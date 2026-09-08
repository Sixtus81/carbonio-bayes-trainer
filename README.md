# Carbonio Bayes Trainer

Serverseitiges Spam-/Ham-Training für Carbonio CE, unabhängig davon, ob Nachrichten mit Outlook, Thunderbird, Apple Mail, iOS, macOS oder dem Carbonio-Webclient verschoben werden.

## Hintergrund

Carbonio erzeugt beim Markieren einer Nachricht als Spam im Webclient einen `SpamReport`. Eine reine IMAP-Verschiebung in den Systemordner `/Junk` löst diesen Vorgang nach bisherigen Tests nicht aus. Dadurch werden Nachrichten, die in externen Clients als Spam markiert werden, nicht von `zmtrainsa` bzw. SpamAssassin gelernt.

Dieses Projekt beobachtet die serverseitigen Ordnerzustände aller konfigurierten Postfächer und trainiert Zustandsänderungen direkt mit `sa-learn`:

- Nachricht erscheint in `/Junk` → als Spam lernen
- Nachricht wurde zuvor als Spam gelernt und wird zurück nach `/Inbox` verschoben → als Ham lernen
- Normale neue Inbox-Nachrichten werden **nicht automatisch** als Ham gelernt
- Bereits verarbeitete Zustände werden in SQLite gespeichert

> Vor dem ersten produktiven Einsatz zunächst mit `dry_run: true` testen.

## Voraussetzungen

- Carbonio CE auf einem Einzelserver oder einem Host mit Zugriff auf `zmmailbox`
- Python 3.10 oder neuer
- `sa-learn`
- Ausführung als Benutzer `zextras` oder über einen passenden Wrapper

## Neuinstallation

Die folgenden Schritte installieren die aktuelle Version vollständig. Die
Konfiguration wird zunächst bewusst im sicheren Testmodus betrieben.

```bash
cd /opt
git clone https://github.com/Sixtus81/carbonio-bayes-trainer.git
cd carbonio-bayes-trainer
python3 -m venv .venv
.venv/bin/pip install .
cp config.example.yaml /etc/carbonio-bayes-trainer.yaml
```

In `/etc/carbonio-bayes-trainer.yaml` mindestens die gewünschten Postfächer
eintragen und `dry_run: true` beibehalten. Danach die Installation und
Carbonio-Anbindung prüfen:

```bash
su - zextras -c '
cd /opt/carbonio-bayes-trainer &&
.venv/bin/carbonio-bayes-trainer \
  --config /etc/carbonio-bayes-trainer.yaml \
  doctor
'
```

Anschließend einen Testlauf ausführen und die Ausgabe kontrollieren:

```bash
su - zextras -c '
cd /opt/carbonio-bayes-trainer &&
.venv/bin/carbonio-bayes-trainer \
  --config /etc/carbonio-bayes-trainer.yaml \
  scan
'
```

Erst nach einem erfolgreichen Test `dry_run: false` setzen. Danach die
systemd-Units installieren und den regelmäßigen Betrieb aktivieren:

```bash
cp systemd/carbonio-bayes-trainer.service /etc/systemd/system/
cp systemd/carbonio-bayes-trainer.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now carbonio-bayes-trainer.timer
systemctl list-timers carbonio-bayes-trainer.timer
```

Zum Abschluss `doctor` und `stats` erneut als Benutzer `zextras` ausführen.

## Betrieb und Diagnose

Für die tägliche Kontrolle stehen zwei read-only Diagnosebefehle zur Verfügung:

```bash
.venv/bin/carbonio-bayes-trainer \
  --config /etc/carbonio-bayes-trainer.yaml \
  doctor

.venv/bin/carbonio-bayes-trainer \
  --config /etc/carbonio-bayes-trainer.yaml \
  stats
```

`doctor` prüft Installation, Konfiguration, Carbonio-Werkzeuge und die
SpamAssassin-Bayes-Datenbank. `stats` zeigt unter anderem:

- bekannte Nachrichten und Stable-Key-Abdeckung
- Spam-/Ham-Trainingsereignisse
- SpamAssassin-Zähler und Token-Anzahl
- Statistiken pro Postfach
- die letzten Scanläufe einschließlich Laufzeit und Fehlern
- einen Health-Status mit konkreter Empfehlung

Ein gesunder Produktionszustand sieht beispielsweise so aus:

```text
Health
------
★★★★★
Overall: Healthy

Recommendation
--------------
No action required.
```

## Konfiguration

Der Abschnitt `carbonio` steuert unter anderem das parallele Einlesen der Mailbox-Ordner:

```yaml
carbonio:
  zmmailbox_path: /opt/zextras/bin/zmmailbox
  inbox_folder: /Inbox
  junk_folder: /Junk
  max_messages_per_folder: 1000
  list_workers: 5
```

`list_workers` legt fest, wie viele Inbox-/Junk-Abfragen gleichzeitig gestartet werden. Der Standardwert ist `5`. Höhere Werte können den Scan weiter beschleunigen, belasten Carbonio aber stärker.

Der Abschnitt `trainer` steuert das SpamAssassin-HOME, die Batch-Größe, parallele Exporte und die maximale Nachrichtengröße für `sa-learn`:

```yaml
trainer:
  sa_learn_path: /opt/zextras/common/bin/sa-learn
  home: /opt/zextras/data/amavisd
  batch_size: 50
  export_workers: 3
  max_message_size: 10485760
```

Carbonio-Amavis verwendet normalerweise die globale Bayes-Datenbank unter:

```text
/opt/zextras/data/amavisd/.spamassassin
```

Mit `trainer.home: /opt/zextras/data/amavisd` verwendet der Trainer dieselbe Bayes-Datenbank wie Amavis im produktiven Mailfluss. Das Training wirkt dadurch global für alle von dieser Amavis-Instanz verarbeiteten Postfächer.

Wird `trainer.home` nicht gesetzt oder auf `null` gesetzt, übernimmt `sa-learn` das HOME des laufenden Prozesses. Auf Carbonio kann dies zur separaten Datenbank `/opt/zextras/.spamassassin` führen und ist daher normalerweise nicht gewünscht.

`max_message_size` wird in Bytes angegeben. Der Standardwert beträgt 10 MiB. Der Wert `0` deaktiviert das Größenlimit. Damit werden auch Nachrichten verarbeitet, die über dem internen Standardlimit von `sa-learn` liegen.

## Upgrade von v0.3.0

Bestehende Konfigurationen müssen um das produktive Amavis-HOME ergänzt werden:

```yaml
trainer:
  home: /opt/zextras/data/amavisd
```

Danach den aktualisierten systemd-Dienst installieren:

```bash
cd /opt/carbonio-bayes-trainer
git pull
.venv/bin/pip install .
cp systemd/carbonio-bayes-trainer.service /etc/systemd/system/
systemctl daemon-reload
.venv/bin/carbonio-bayes-trainer --config /etc/carbonio-bayes-trainer.yaml doctor
```

Falls ältere Versionen bereits trainiert haben, lagen diese Lernvorgänge möglicherweise in `/opt/zextras/.spamassassin`. Nach dem Upgrade sollten Ham-Bootstrap und Spam-Training kontrolliert gegen die produktive Datenbank erneut ausgeführt werden.

## Upgrade auf v0.4.1

Dieser Abschnitt gilt nur für eine bereits vorhandene Installation. Für neue
Systeme bitte die vollständige Anleitung unter [Neuinstallation](#neuinstallation)
verwenden.

Für ein Upgrade aus dem Git-Checkout:

```bash
cd /opt/carbonio-bayes-trainer
git pull --ff-only
.venv/bin/pip install .
cp systemd/carbonio-bayes-trainer.service /etc/systemd/system/
cp systemd/carbonio-bayes-trainer.timer /etc/systemd/system/
systemctl daemon-reload
systemctl restart carbonio-bayes-trainer.timer
```

Danach den Zustand kontrollieren:

```bash
su - zextras -c '
cd /opt/carbonio-bayes-trainer &&
.venv/bin/carbonio-bayes-trainer \
  --config /etc/carbonio-bayes-trainer.yaml \
  doctor
'

su - zextras -c '
cd /opt/carbonio-bayes-trainer &&
.venv/bin/carbonio-bayes-trainer \
  --config /etc/carbonio-bayes-trainer.yaml \
  stats
'
```

Das Upgrade verändert vorhandene Bayes-Daten nicht. Bei Installationen mit
alten State-Einträgen können die administrativen Befehle
`migrate-stable-keys` und `cleanup-legacy` verwendet werden. Vor einer
Bereinigung immer zuerst den jeweiligen Dry-Run ausführen. `cleanup-legacy`
entfernt ausschließlich alte SQLite-State-Zeilen; SpamAssassin-Bayes-Daten und
die Trainingshistorie bleiben unverändert.

## systemd

```bash
cp systemd/carbonio-bayes-trainer.service /etc/systemd/system/
cp systemd/carbonio-bayes-trainer.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now carbonio-bayes-trainer.timer
```

Der mitgelieferte Timer verwendet standardmäßig einen festen 15-Minuten-Rhythmus über `OnCalendar=*:0/15`. Dieses Intervall ist für Installationen mit bis zu ungefähr 50 Postfächern in der Regel ausreichend, sofern die überwachten Inbox-/Junk-Ordner einigermaßen gepflegt sind und ein vollständiger Scan deutlich innerhalb des Intervalls abgeschlossen wird.

Bei größeren Installationen, sehr großen Ordnern oder längeren Scan-Laufzeiten sollte das Timer-Intervall an die tatsächliche Umgebung angepasst werden. Als Faustregel sollte zwischen zwei geplanten Starts genügend Reserve für die längeren beobachteten Scans verbleiben. Ein kürzeres Intervall beschleunigt das Bayes-Training nur begrenzt, kann aber unnötige Überschneidungen verursachen, wenn ein vorheriger Lauf noch aktiv ist.

Die reale Scan-Dauer kann mit `carbonio-bayes-trainer stats` unter `Recent scans` kontrolliert werden. Der Health-Check `Scan freshness` hilft zusätzlich dabei zu erkennen, wenn geplante Läufe nicht mehr regelmäßig stattfinden.

Beispiel für eine Anpassung auf 30 Minuten:

```ini
[Timer]
OnCalendar=*:0/30
```

Nach einer Änderung der Timer-Datei:

```bash
systemctl daemon-reload
systemctl restart carbonio-bayes-trainer.timer
systemctl list-timers carbonio-bayes-trainer.timer
```

Der Dienst erlaubt Schreibzugriffe auf die eigene SQLite-Datenbank und auf die produktive SpamAssassin-Bayes-Datenbank unter `/opt/zextras/data/amavisd/.spamassassin`. Diese Freigabe wird unter anderem für `bayes.mutex`, `bayes_seen`, `bayes_toks` und `bayes_journal` benötigt.

Status und Protokoll:

```bash
systemctl status carbonio-bayes-trainer.timer
journalctl -u carbonio-bayes-trainer.service -f
```

## Funktionsweise

Der Trainer fragt je Postfach die Nachrichten in `/Inbox` und `/Junk` über `zmmailbox` ab. Diese Ordnerabfragen werden parallel ausgeführt; die weitere Verarbeitung und die SQLite-Zugriffe bleiben deterministisch und sequenziell. Für jede Nachricht wird der letzte bekannte Ordnerzustand gespeichert.

| Vorheriger Zustand | Neuer Zustand | Aktion |
|---|---|---|
| unbekannt | Junk | Spam lernen |
| Inbox | Junk | Spam lernen |
| Junk / als Spam gelernt | Inbox | Ham lernen |
| unbekannt | Inbox | keine Aktion |

Carbonio kann beim Verschieben einer Nachricht die interne Mailbox-ID ändern. Deshalb verwendet der Trainer zusätzlich eine stabile Nachrichtenidentität auf Basis der RFC822-`Message-ID`; fehlt diese, wird ein SHA256-Wert der vollständigen Nachricht verwendet.

Die Originalnachricht wird nur temporär exportiert und anschließend an `sa-learn --spam` oder `sa-learn --ham` übergeben. Dabei setzt der Trainer außerdem `--max-size` entsprechend der Konfiguration und verwendet das konfigurierte SpamAssassin-HOME.

Der Befehl `doctor` zeigt das wirksame SpamAssassin-HOME, den Bayes-Pfad und die Zähler für Spam, Ham und Tokens an. Fehlen im konfigurierten HOME die Dateien `bayes_toks`, `bayes_seen` oder `bayes_journal`, wird eine Warnung ausgegeben.

## Produktiv validiert

Version 0.4.1 wurde vom 10. August bis zum 8. September 2026 vier Wochen lang
auf einer produktiven Carbonio-CE-Installation getestet. Der Abschlussstand:

- 16.064 bekannte Nachrichten
- 16.064 Stable Keys, 0 Legacy Keys und damit 100 % Abdeckung
- 9.549 Spam- und 9 Ham-Trainingsereignisse
- produktive Bayes-Datenbank mit 14.497 Spam und 96.911 Ham
- 0 fehlgeschlagene Nachrichten in der jüngsten Scan-Historie
- regelmäßiger 10-Minuten-Betrieb
- jüngste Laufzeiten zwischen ca. 83 und 116 Sekunden
- Health-Status `★★★★★` und `Overall: Healthy`

Die produktive Installation verwendet:

- 30 Mailkonten
- `list_workers: 5`
- `batch_size: 50`
- `export_workers: 3`
- `max_message_size: 10485760`

Bereits Version 0.2.2 verkürzte durch paralleles Mailbox-Listing einen
vollständigen Scan mit 7.090 Nachrichten von ca. 3:57 auf 1:26 Minuten. Die
v0.4.1-Validierung bestätigt darüber hinaus den stabilen Dauerbetrieb der
Statistik-, Health-, Lock- und Stable-Key-Funktionen.

## Sicherheit

- Keine Passwörter werden benötigt, wenn `zmmailbox -z` als berechtigter Carbonio-Benutzer ausgeführt wird.
- Temporäre Nachrichtendateien werden mit restriktiven Dateirechten erzeugt und nach dem Training gelöscht.
- `dry_run` ist standardmäßig aktiviert.
- Die SQLite-Datei sollte nur für den Dienstbenutzer lesbar sein.
- Der systemd-Dienst läuft als `zextras` mit `NoNewPrivileges=true`, `ProtectHome=true` und `ProtectSystem=full`.

## Noch zu verifizieren

Carbonio-/Zimbra-Versionen können sich in der Ausgabe und den REST-Pfaden von `zmmailbox` unterscheiden. Deshalb sind Such- und Exportargumente in der YAML-Datei konfigurierbar. Vor dem Aktivieren des echten Trainings bitte die Ausgabe auf dem Zielsystem prüfen.

## Lizenz

MIT
