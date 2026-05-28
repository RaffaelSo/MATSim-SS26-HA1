================================================================
MATSim Analyse – Dresdner Altstadt Tempo-10-Zone
TU Berlin | MATSim UE Planning | SoSe 2026
================================================================

INHALT DIESES ORDNERS
---------------------
analyse_affected_agents.py      Hauptscript (Python)
base_experienced_plans.xml      MATSim Output – Base Case (Pläne)
policy_experienced_plans.xml    MATSim Output – Policy Case (Pläne)
base_trips.csv                  MATSim Output – Base Case (Trips)
policy_trips.csv                MATSim Output – Policy Case (Trips)
changeset.json                  Changeset – 557 Tempo-10-Links
README.txt                      Diese Datei

VORAUSSETZUNGEN
---------------
Python 3.9 oder neuer
Benötigte Bibliotheken (alle Standard):
  pip install pandas

AUSFÜHRUNG
----------
1. Alle Dateien dieses Ordners in dasselbe Verzeichnis legen.
2. Terminal / Eingabeaufforderung in diesem Verzeichnis öffnen.
3. Script starten:

   python analyse_affected_agents.py

4. Ergebnisse erscheinen im Unterordner "ergebnisse/" als CSV-Dateien:
   - block3_basic_analyse.csv   (Modal Split, Distanz, Reisezeit)
   - block3_modal_split.csv     (Modal Split Detail)
   - block4_bleiber_verlasser.csv (Wer bleibt, wer geht?)
   - block4_modal_bleiber.csv   (Modal Split der Bleiber)
   - block4_score_delta.csv     (Score-Veränderung pro Agent)

LAUFZEIT
--------
Ca. 2–5 Minuten (abhängig vom Rechner),
da beide XML-Dateien (~125 MB) zeilenweise eingelesen werden.

SCRIPT-STRUKTUR
---------------
Block 1 – Affected Agents identifizieren
          (Changeset-Links + experienced_plans Base Case)
Block 2 – Untergruppen bilden (Durchgang / Ziel / Anwohner)
          + Summen-Validierungscheck
Block 3 – Basic-Analyse: Modal Split, Trips, Distanz, Reisezeit
          (Basis: output_trips.csv)
Block 4 – Deep Dive: Wer bleibt/verlässt die Zone?
          Score-Delta, Modal Split der Bleiber
          (Basis: experienced_plans Policy Case)

HINWEIS ZUR SAMPLE-SIZE
------------------------
Das Modell simuliert 1 % der Dresdner Bevölkerung.
Für Realwelt-Aussagen alle absoluten Zahlen × 100 rechnen.
================================================================
