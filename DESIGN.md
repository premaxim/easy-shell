# Patchbay – Design-Plan

## Leitidee

Ein aufgeräumtes Patchpanel im Serverschrank. Jeder Server ist ein Port mit
Status-LED, jede Gruppe hat eine Kabelfarbe. Der **Kabelstreifen** ist das eine
prägende Element: 4 px breit, links an jeder Server-Zeile und als Markierung
am Terminal-Tab. Alles andere ist ruhig: flache Flächen, feine Linien, keine
Schatten, keine Verläufe.

## Tokens

| Token        | Dark (Standard) | Light (abgeleitet) | Verwendung                         |
|--------------|-----------------|--------------------|------------------------------------|
| grund        | `#14202B`       | `#EEF3F6`          | Fenster, Terminal-Hintergrund      |
| flaeche      | `#1B2B39`       | `#F8FAFB`          | Seitenleiste, Dialoge, Popover     |
| linie        | `#2C4152`       | `#C8D5DE`          | Trennlinien, Eingabefeld-Rahmen    |
| text         | `#E4ECF1`       | `#14202B`          | Primärtext                         |
| text-leise   | `#8DA2B2`       | `#4D6475`          | user@host, Gruppenköpfe, Hinweise  |
| led-online   | `#5DB98C`       | `#2E8A5F`          | nur LED                            |
| led-offline  | `#CC6470`       | `#B3434F`          | nur LED (und destruktive Buttons)  |
| led-pruefen  | `#D9B95B`       | `#9C7A1E`          | nur LED                            |
| akzent       | `#4A8BD4`       | `#2F6DB5`          | Fokusring, primärer Button         |

Kabelfarben: Blau `#4A8BD4`, Gelb `#D9B95B`, Grau `#9AA7B1`, Rot `#CC6470`,
Grün `#5DB98C`, Violett `#9B7FD1` – in beiden Themes gleich, weil echte Kabel
auch nicht die Farbe wechseln.

Abstände: 4-px-Raster (4 / 8 / 12 / 16 / 24). Ein Radius: 6 px für Buttons und
Eingaben, Zeilen haben keinen Radius. Keine Schatten außer den von libadwaita
gezeichneten Dialog-Schatten.

Typografie: Atkinson Hyperlegible Next (im Flatpak gebündelt), Fallback
System-Sans. Drei Größen: 15 px Text, 13 px leise Zeilen, 20 px Überschrift
der Startfläche. Gewichte 400 und 600. Sentence case überall.
JetBrains Mono ausschließlich im Terminal (einstellbar).

## Layout

- `Adw.OverlaySplitView`: links Seitenleiste (280 px), rechts Tabs.
  Unter 720 px klappt die Seitenleiste ein (Steam Deck im Hochformat,
  kleine Fenster); 1280×800 zeigt beides.
- Server-Zeile, 56 px hoch: Kabelstreifen · LED · Name / leise `user@host` ·
  Menü-Button (44×44). Gruppen sind einfache Abschnittsköpfe mit Linie.
- LEDs unterscheiden sich auch in der **Form**, nicht nur in der Farbe:
  erreichbar = gefüllt, nicht erreichbar = Ring, prüfe = halb gefüllt.
- Rechts `Adw.TabView` + `Adw.TabBar`, jeder Tab trägt den Kabelstreifen
  als Icon. Ohne Session: Startfläche mit zuletzt genutzten Servern und zwei
  Handlungen.
- Bearbeiten im `Adw.Dialog` (wird auf schmalen Fenstern zum Bottom-Sheet).

## Bewegung

Nur libadwaita-eigene Übergänge (Tab öffnen, Dialog, Split-View) und eine
150-ms-Farbüberblendung der LED. GTK schaltet beides ab, wenn
„Animationen reduzieren“ aktiv ist.

## Prüfung gegen die Verbotsliste

| Regel                                  | Erster Entwurf                       | Korrektur |
|----------------------------------------|--------------------------------------|-----------|
| Kein Orange/Terrakotta/Kupfer, kein Creme | Light-Grund war zuerst `#F5F1EA` (warmes Papier) | → kühles `#EEF3F6`, gleiche Petrol-Familie wie Dark |
| Kein Fast-Schwarz + Neongrün            | Online-LED als einziger Akzent auf `#14202B` wirkte wie Hacker-Look | → Akzent ist Kabel-Blau; Grün kommt nur in LEDs vor, nie als Text- oder Flächenfarbe |
| Keine identischen Karten mit Schatten   | Startfläche war als Kachelraster „zuletzt genutzt“ geplant | → einfache Liste aus Zeilen im selben Stil wie die Seitenleiste |
| Keine VERSALIEN, keine „A · B · C“-Zeilen, kein „→“ | Gruppenköpfe in Kapitälchen; Zeile „user · host · port“ | → Gruppenköpfe in normalem Satz; Unterzeile ist `user@host` (Port nur, wenn ≠ 22, als `:2222`) |
| Monospace nur im Terminal               | Host/IP in der Liste war in Mono gesetzt | → Atkinson mit `tabular-nums` für Ziffern |
| Adwaita-Standard-Look                   | `Adw.StatusPage` mit großem Icon als Leerzustand | → eigene, ruhige Startfläche ohne Symbolbild |

## Was die App unverwechselbar macht

1. Der Kabelstreifen verbindet Liste und Tab sichtbar: dieselbe Farbe links an
   der Zeile und am offenen Tab – man „steckt“ ein Kabel.
2. LEDs mit Form-Codierung statt farbiger Badges.
3. Petrol-Tinte statt Neutralgrau als Grundton, in Terminal und UI identisch,
   damit Terminal und Oberfläche eine Fläche bilden.

## Abschlussprüfung („Chanel-Regel“)

Nach den ersten Screenshots habe ich ein Element entfernt: den **App-Titel
„Patchbay“ in der Kopfleiste der Seitenleiste**. Er wiederholte nur den
Fenstertitel. Die Suche nimmt jetzt seinen Platz ein. Das spart auf dem
Steam Deck (800 px Höhe) eine ganze Zeile, und die Seitenleiste beginnt direkt
mit dem, was man dort tut: suchen und verbinden.

Weitere Korrekturen aus der Screenshot-Prüfung:
- Die LEDs auf der Startfläche blieben auf „prüfe…“ stehen. Sie hängen jetzt
  am selben Status-Monitor wie die Liste.
- Die Tab-Leiste war unsichtbar (`show-title=False` verbirgt auch das Titel-Widget).
- Die Seitenleiste startete eingeklappt (falsche Bindungsrichtung).
