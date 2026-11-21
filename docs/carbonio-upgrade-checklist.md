# Carbonio-Post-Upgrade-Checkliste

Diese Checkliste dient zur Kontrolle einer Carbonio-Installation, auf der der
Carbonio Bayes Trainer betrieben wird. Sie ergänzt die offiziellen
Upgrade-Anweisungen von Carbonio, ersetzt sie aber nicht.

Die Postfix-/Anti-Spoof-Prüfungen gehören zur Carbonio-Mailserver-Konfiguration
und nicht zum Carbonio Bayes Trainer. Sie sind hier enthalten, weil ein
Carbonio-Upgrade diese Einstellungen oder deren wirksame Generierung verändern
kann.

## Vor dem Upgrade

- Aktuelles Backup oder Snapshot erstellen und die Wiederherstellungsmöglichkeit
  prüfen.
- Die offiziellen Upgrade-Hinweise für die installierte und die Zielversion
  lesen.
- Geplante Paketänderungen und den Ist-Zustand dokumentieren:

  ```bash
  apt-get -s full-upgrade
  dpkg-query -W 'carbonio*' 2>/dev/null
  systemctl --failed
  ```

- Die aktuell wirksamen Postfix-Regeln sichern:

  ```bash
  /opt/zextras/common/sbin/postconf -n |
    grep -E '^(content_filter|smtpd_sender_login_maps|smtpd_sender_restrictions)'
  ```

- Trainer, Timer und letzte Scanergebnisse kontrollieren:

  ```bash
  systemctl status carbonio-bayes-trainer.timer --no-pager

  su - zextras -c '
  cd /opt/carbonio-bayes-trainer &&
  .venv/bin/carbonio-bayes-trainer \
    --config /etc/carbonio-bayes-trainer.yaml doctor
  '

  su - zextras -c '
  cd /opt/carbonio-bayes-trainer &&
  .venv/bin/carbonio-bayes-trainer \
    --config /etc/carbonio-bayes-trainer.yaml stats
  '
  ```

## Upgrade durchführen

- Das Upgrade ausschließlich nach der offiziellen Carbonio-Anleitung für die
  konkrete Zielversion durchführen.
- Eine vorhandene `localconfig.xml` beibehalten, falls die Paketverwaltung
  danach fragt.
- `pending-setups -a` nur ausführen, wenn es in den offiziellen Hinweisen für
  dieses Upgrade verlangt wird.
- Den Server neu starten, wenn die Upgrade-Anleitung oder aktualisierte
  Kernkomponenten dies erfordern.

## Direkt nach dem Upgrade

### Pakete und Dienste

```bash
dpkg --audit
apt-get -s -f install
systemctl --failed
systemctl status carbonio-configd.service --no-pager -l
```

`dpkg --audit` und die simulierte Reparatur sollten keine offenen
Paketprobleme melden. `systemctl --failed` sollte keine fehlgeschlagenen Units
anzeigen.

Falls `carbonio-configd` bereits während eines Java-Updates lief, können die
geladene Java-Version und `jspawnhelper` nicht mehr zusammenpassen. In diesem
Fall erscheinen beispielsweise Meldungen wie `Incorrect Java version` oder
`Failed to exec spawn helper`. Die zugehörigen Protokolle prüfen:

```bash
journalctl -u carbonio-configd.service -b --no-pager |
  grep -Ei 'jspawnhelper|Incorrect Java version|spawn helper|exception'
```

Bei einem solchen Befund `carbonio-configd` kontrolliert neu starten und den
Status anschließend erneut prüfen:

```bash
systemctl restart carbonio-configd.service
systemctl status carbonio-configd.service --no-pager -l
```

### Mailfluss und Anti-Spoof-Regeln

```bash
/opt/zextras/common/sbin/postconf -n |
  grep -E '^(content_filter|smtpd_sender_login_maps|smtpd_sender_restrictions)'
```

Für die hier getestete Einzelserver-Konfiguration werden insbesondere folgende
wirksamen Bestandteile erwartet:

- `content_filter` verweist auf Amavis.
- `smtpd_sender_login_maps` verweist auf die Carbonio-LDAP-Map.
- `smtpd_sender_restrictions` enthält `reject_sender_login_mismatch`.

Die vollständige Reihenfolge kann je nach Carbonio-Version und Installation
abweichen. Deshalb immer mit dem vor dem Upgrade gesicherten Zustand und der
offiziellen Dokumentation vergleichen.

### Carbonio Bayes Trainer

```bash
systemctl status carbonio-bayes-trainer.timer --no-pager
systemctl list-timers carbonio-bayes-trainer.timer --no-pager
```

Nach dem ersten geplanten Lauf:

```bash
systemctl status carbonio-bayes-trainer.service --no-pager -l
journalctl -u carbonio-bayes-trainer.service -b --no-pager

su - zextras -c '
cd /opt/carbonio-bayes-trainer &&
.venv/bin/carbonio-bayes-trainer \
  --config /etc/carbonio-bayes-trainer.yaml doctor
'

su - zextras -c '
cd /opt/carbonio-bayes-trainer &&
.venv/bin/carbonio-bayes-trainer \
  --config /etc/carbonio-bayes-trainer.yaml stats
'
```

Abnahmekriterien:

- Der Timer ist `active (waiting)` und hat einen plausiblen nächsten Termin.
- Der letzte Trainer-Lauf wurde ohne Fehler beendet.
- `doctor` meldet keine Fehler und verwendet als SpamAssassin-HOME den in der
  Konfiguration vorgesehenen Pfad, üblicherweise `/opt/zextras/data/amavisd`.
- `stats` zeigt keine fehlgeschlagenen aktuellen Scans.
- Known-/Stable-Zähler und Trainingsdaten sind nach dem Upgrade weiterhin
  vorhanden; die Stable-Key-Abdeckung ist nicht unerwartet eingebrochen.
- Die Scan-Dauer bleibt mit ausreichender Reserve unter dem Timer-Intervall.

Der Trainer-Dienst ist als `Type=oneshot` ausgeführt. Nach einem erfolgreichen
Lauf ist deshalb `inactive (dead)` normal. Entscheidend sind Exit-Code,
Journal und der aktive Timer. Durch parallele Worker kann außerdem die addierte
CPU-Zeit höher als die reale Laufzeit sein.

## Warnung „Detected unsafe path transition“

Diese Warnung kann bei der Verarbeitung von systemd-tmpfiles-Regeln auftreten,
wenn sich Eigentümer eines Elternpfads und eines darunterliegenden Pfads
unterscheiden. Sie beweist für sich allein weder einen Trainer-Fehler noch eine
defekte Carbonio-Installation.

Nicht pauschal `chown -R` auf `/opt/zextras` oder Unterverzeichnisse anwenden.
Zuerst Paketstatus, tatsächliche Eigentümer und Paketzuständigkeit prüfen:

```bash
dpkg --audit
systemctl --failed
stat -c '%U:%G %a %n' /opt/zextras/conf /opt/zextras/jetty_base/common
dpkg -S /opt/zextras/conf/zmconfigd.cf \
  /opt/zextras/conf/amavisd.conf.in \
  /opt/zextras/jetty_base/common/lib 2>/dev/null
```

Erst wenn ein Dienst fehlschlägt oder Paketdateien nachweislich falsche
Eigentümer haben, sollte gezielt anhand der Paketvorgaben korrigiert werden.

## Ergebnisse dokumentieren

Vorher-/Nachher-Ausgaben zusammen mit Carbonio-Version, Datum und Upgrade-Pfad
ablegen. Vor dem Veröffentlichen in Issues oder Foren Postfachadressen,
Domains, Message-IDs, Betreffzeilen und andere personenbezogene Daten
unkenntlich machen.
