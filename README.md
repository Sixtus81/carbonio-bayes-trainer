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

## Installation

```bash
cd /opt
git clone https://github.com/Sixtus81/carbonio-bayes-trainer.git
cd carbonio-bayes-trainer
python3 -m venv .venv
.venv/bin/pip install .
cp config.example.yaml /etc/carbonio-bayes-trainer.yaml
```

Konfiguration prüfen und zunächst im Testmodus starten:

```bash
.venv/bin/carbonio-bayes-trainer \
  --config /etc/carbonio-bayes-trainer.yaml \
  doctor
```

## Konfiguration

Der Abschnitt `trainer` steuert Batch-Größe, parallele Exporte und die maximale Nachrichtengröße für `sa-learn`:

```yaml
trainer:
  sa_learn_path: /opt/zextras/common/bin/sa-learn
  batch_size: 50
  export_workers: 3
  max_message_size: 10485760
```

`max_message_size` wird in Bytes angegeben. Der Standardwert beträgt 10 MiB. Der Wert `0` deaktiviert das Größenlimit. Damit werden auch Nachrichten verarbeitet, die über dem internen Standardlimit von `sa-learn` liegen.

## systemd

```bash
cp systemd/carbonio-bayes-trainer.service /etc/systemd/system/
cp systemd/carbonio-bayes-trainer.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now carbonio-bayes-trainer.timer
```

Der Dienst erlaubt Schreibzugriffe auf die eigene SQLite-Datenbank und auf die SpamAssassin-Bayes-Datenbank unter `/opt/zextras/.spamassassin`. Diese Freigabe wird für `bayes.mutex`, `bayes_seen` und `bayes_toks` benötigt.

Status und Protokoll:

```bash
systemctl status carbonio-bayes-trainer.timer
journalctl -u carbonio-bayes-trainer.service -f
```

## Funktionsweise

Der Trainer fragt je Postfach die Nachrichten in `/Inbox` und `/Junk` über `zmmailbox` ab. Für jede Nachricht wird der letzte bekannte Ordnerzustand gespeichert.

| Vorheriger Zustand | Neuer Zustand | Aktion |
|---|---|---|
| unbekannt | Junk | Spam lernen |
| Inbox | Junk | Spam lernen |
| Junk / als Spam gelernt | Inbox | Ham lernen |
| unbekannt | Inbox | keine Aktion |

Die Originalnachricht wird nur temporär exportiert und anschließend an `sa-learn --spam` oder `sa-learn --ham` übergeben. Dabei setzt der Trainer außerdem `--max-size` entsprechend der Konfiguration.

## Produktiv validiert

Version 0.2.0 wurde auf einer produktiven Carbonio-CE-Installation mit folgender Konfiguration getestet:

- 30 Mailkonten
- 6936 geprüfte Nachrichten
- 6936 erfolgreich verarbeitet
- 0 Fehler
- `batch_size: 50`
- `export_workers: 3`
- `max_message_size: 10485760`

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
