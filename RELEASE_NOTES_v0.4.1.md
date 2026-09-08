# Carbonio Bayes Trainer v0.4.1

Version 0.4.1 bündelt die Betriebs- und Diagnosefunktionen der 0.4-Serie und
markiert den erfolgreichen Abschluss eines vierwöchigen Produktionstests.

## Highlights

- `stats` mit State-, Bayes-, Mailbox- und Scan-Statistiken
- Health-Auswertung mit Sternen, Einzelprüfungen und Empfehlungen
- persistente Historie der letzten Scanläufe
- Schutz vor gleichzeitig laufenden Scans
- 100%ige Stable-Key-Abdeckung im validierten Produktivbetrieb
- kontrollierte Migration und Bereinigung alter State-Einträge
- Zeitangaben in der lokalen Zeitzone des Servers

## Stable Message State

Carbonio kann die interne Nachrichten-ID beim Verschieben einer Nachricht
ändern. Der Trainer verwendet deshalb die RFC822-`Message-ID` und einen
SHA256-Fallback als stabile Identität.

Version 0.4.1 ergänzt dazu zwei sichere Verwaltungswege:

- Noch sichtbare Legacy-Nachrichten erhalten während normaler Scans ihren
  Stable Key, ohne erneut als Spam oder Ham trainiert zu werden.
- Nicht mehr erreichbare Legacy-Zeilen können explizit mit `cleanup-legacy`
  aus der SQLite-State-Datenbank entfernt werden.

Die Bereinigung verändert weder SpamAssassin-Bayes-Daten noch die gespeicherte
Trainingshistorie. Vor produktiven Verwaltungsbefehlen sollte stets der
zugehörige Dry-Run verwendet werden.

## Monitoring und Betrieb

`carbonio-bayes-trainer stats` zeigt jetzt:

- bekannte, stabile und alte Nachrichten-State-Einträge
- Spam- und Ham-Trainingsereignisse
- SpamAssassin-Zähler und bekannte Tokens
- Werte pro Mailbox
- die letzten Scanläufe mit Dauer und Fehlerzahl
- eine zusammenfassende Health-Bewertung

Ein nicht blockierendes Prozess-Lock verhindert parallele Scans. Wird bereits
ein Scan ausgeführt, beendet sich ein zweiter Prozess kontrolliert mit
Exit-Code 75, statt die Laufstatistik zu verfälschen.

Der systemd-Timer verwendet standardmäßig einen festen 15-Minuten-Rhythmus.
Das Intervall kann anhand der unter `Recent scans` sichtbaren Laufzeiten an die
jeweilige Installation angepasst werden.

## Production validation

The release was continuously validated on a production Carbonio CE server
from 2026-08-10 through 2026-09-08:

- 30 mail accounts
- 16,064 known message states
- 16,064 stable keys and 0 legacy rows
- 9,549 Spam and 9 Ham training events
- production Bayes database with 14,497 Spam and 96,911 Ham messages
- no failed messages in the final recent-scan history
- regular 10-minute scheduling
- recent scan durations between 83 and 116 seconds
- final health status: five stars, `Overall: Healthy`

## Upgrade

```bash
cd /opt/carbonio-bayes-trainer
git pull --ff-only
.venv/bin/pip install .
cp systemd/carbonio-bayes-trainer.service /etc/systemd/system/
cp systemd/carbonio-bayes-trainer.timer /etc/systemd/system/
systemctl daemon-reload
systemctl restart carbonio-bayes-trainer.timer
```

Verify the installation afterwards:

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

No configuration change is required when upgrading from a correctly
configured v0.4.0 installation.
