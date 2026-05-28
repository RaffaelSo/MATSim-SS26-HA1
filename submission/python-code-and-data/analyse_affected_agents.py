# =============================================================================
# MATSim Analyse – Dresdner Altstadt Tempo-10-Zone
# TU Berlin, MATSim UE Planning, SoSe 2026
#
# Dieses Script analysiert, welche Agenten im Dresden-Szenario direkt von der
# Tempo-10-Maßnahme in der Altstadt betroffen sind. Es ist in vier Blöcke
# gegliedert, die aufeinander aufbauen:
#
#   Block 1 – Affected Agents identifizieren
#   Block 2 – Untergruppen bilden (Anwohner / Zielverkehr / Durchgangsverkehr)
#   Block 3 – Basic-Analyse (Modal Split, Trips, Distanz, Reisezeit)
#   Block 4 – Deep Dive: Wer bleibt nach Tempo-10 in der Zone?
#
# Benötigte Eingabedateien (im selben Ordner wie dieses Script):
#   - base_experienced_plans.xml
#   - policy_experienced_plans.xml
#   - base_trips.csv
#   - policy_trips.csv
#   - changeset.json
#
# Ausgabe: CSV-Tabellen im Ordner "ergebnisse/"
# Sample-Size: 1% → Hochrechnung ×100 für Realweltzahlen
# =============================================================================

import re
import json
import os
import pandas as pd

# -----------------------------------------------------------------------------
# Konfiguration: Pfade und Einstellungen
# -----------------------------------------------------------------------------
BASE_PLANS   = "base_experienced_plans.xml"
POLICY_PLANS = "policy_experienced_plans.xml"
BASE_TRIPS   = "base_trips.csv"
POLICY_TRIPS = "policy_trips.csv"
CHANGESET    = "changeset.json"
OUTPUT_DIR   = "ergebnisse"
SAMPLE_FAKTOR = 100  # 1%-Sample → Hochrechnung auf Realwelt

os.makedirs(OUTPUT_DIR, exist_ok=True)

# MATSim-interne Aktivitätstypen, die keine echten Aktivitäten darstellen
# (werden bei der Gruppenklassifikation ignoriert)
INTERAKTION_TYPEN = {
    'car interaction', 'bike interaction', 'truck8t interaction',
    'truck18t interaction', 'truck40t interaction', 'ride interaction'
}

# Verkehrsmodi, die von Tempo-10 betroffen sind
# (ÖPNV fährt auf separaten Links und ist nicht betroffen)
RELEVANTE_MODI = {'car', 'bike', 'ride', 'truck8t', 'truck18t', 'truck40t'}

print("=" * 65)
print("MATSim Analyse – Dresdner Altstadt Tempo-10-Zone")
print("=" * 65)


# =============================================================================
# BLOCK 1: AFFECTED LINKS AUS CHANGESET LADEN & AFFECTED AGENTS IDENTIFIZIEREN
# =============================================================================
# Ziel: Herausfinden, welche Agenten im Base Case mindestens einmal mit
#       einem motorisierten Verkehrsmittel (Car, Bike, Truck) über einen
#       der von Tempo-10 betroffenen Links gefahren sind.
#
# Datenquelle:
#   - changeset.json       → liefert die Link-IDs der Tempo-10-Zone
#   - base_experienced_plans.xml → enthält die tatsächlich gefahrenen Routen
#
# Methodik:
#   Die experienced_plans XML enthält für jedes Leg mit Straßenroute eine
#   Leerzeichen-separierte Liste aller passierten Link-IDs im <route>-Tag.
#   Wir lesen die Datei zeilenweise und prüfen für jedes motorisierte Leg,
#   ob die Route einen Changeset-Link enthält.
# =============================================================================

print("\n[Block 1] Lade Changeset und identifiziere betroffene Links...")

# --- 1a: Link-IDs aus dem Changeset extrahieren ---
# Der Changeset hat eine verschachtelte JSON-Struktur:
# modifications[0].payload.modifications[i].payload.id gibt die Link-ID

with open(CHANGESET, 'r', encoding='utf-8') as f:
    cs = json.load(f)

affected_links = set()
for mod in cs['modifications'][0]['payload']['modifications']:
    link_id = mod['payload']['id']
    affected_links.add(str(link_id))

print(f"  Changeset geladen: {len(affected_links)} betroffene Links (Tempo-10-Zone)")

# --- 1b: Experienced Plans Base Case einlesen ---
# Für jeden Agenten wird gespeichert:
#   - activities: Liste aller (Aktivitätstyp, Link-ID) Tupel des Tages
#   - affected:   True wenn mind. 1 motorisiertes Leg einen Changeset-Link nutzt
#   - score:      Tages-Score (Nutzenwert) aus dem Plan

re_person = re.compile(r'<person id="([^"]+)"')
re_plan   = re.compile(r'<plan score="([^"]+)"')
re_leg    = re.compile(r'<leg mode="([^"]+)"')
re_dep    = re.compile(r'dep_time="([^"]+)"')
re_trav   = re.compile(r'trav_time="([^"]+)"')
re_act    = re.compile(r'<activity type="([^"]+)"[^>]*link="([^"]+)"')
re_route  = re.compile(r'<route type="links"[^>]*>([^<]*)</route>')

def parse_plans(filepath):
    """
    Liest eine MATSim experienced_plans.xml zeilenweise ein.
    Gibt ein Dictionary zurück: {person_id: {'score': float, 'activities': [...],
                                              'affected': bool}}
    """
    personen = {}
    current_id    = None
    current_score = None
    current_mode  = None
    current_dep   = None
    current_trav  = None
    acts_buf = []
    is_affected = False

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:

            # Neue Person beginnt → vorherige Person speichern
            if '<person id=' in line:
                if current_id is not None:
                    personen[current_id] = {
                        'score':      current_score,
                        'activities': acts_buf,
                        'affected':   is_affected
                    }
                pm = re_person.search(line)
                current_id    = pm.group(1) if pm else None
                current_score = None
                current_mode  = None
                current_dep   = None
                current_trav  = None
                acts_buf      = []
                is_affected   = False
                continue

            # Plan-Score: Nutzenwert des gesamten simulierten Tages
            if '<plan score=' in line:
                sm = re_plan.search(line)
                if sm:
                    current_score = float(sm.group(1))
                continue

            # Aktivität: Typ und zugehöriger Link werden gespeichert
            if '<activity type=' in line:
                am = re_act.search(line)
                if am:
                    acts_buf.append((am.group(1), am.group(2)))
                continue

            # Neues Leg: Modus und Zeitangaben merken
            if '<leg mode=' in line:
                lm = re_leg.search(line)
                dm = re_dep.search(line)
                tm = re_trav.search(line)
                current_mode = lm.group(1) if lm else None
                current_dep  = dm.group(1) if dm else None
                current_trav = tm.group(1) if tm else None
                continue

            # Zeitangaben können in Folgezeilen stehen
            if current_mode in RELEVANTE_MODI:
                if current_dep is None and 'dep_time=' in line:
                    dm = re_dep.search(line)
                    if dm: current_dep = dm.group(1)
                if current_trav is None and 'trav_time=' in line:
                    tm = re_trav.search(line)
                    if tm: current_trav = tm.group(1)

            # Route mit Links: Herzstück der Betroffenheits-Prüfung
            # Nur motorisierte Legs haben den Typ "links" (walk/pt nicht)
            if '<route type="links"' in line and current_mode in RELEVANTE_MODI:
                rm = re_route.search(line)
                if rm:
                    # Alle Link-IDs der Route als Menge
                    route_links = set(rm.group(1).split())
                    # Schnittmenge mit Changeset-Links prüfen
                    if route_links & affected_links:
                        is_affected = True

    # Letzte Person speichern
    if current_id is not None:
        personen[current_id] = {
            'score':      current_score,
            'activities': acts_buf,
            'affected':   is_affected
        }
    return personen

print("  Lese Base Case experienced plans...")
base_personen   = parse_plans(BASE_PLANS)
print("  Lese Policy Case experienced plans...")
policy_personen = parse_plans(POLICY_PLANS)

# Affected agents = alle Personen mit mind. 1 betroffenem Leg im Base Case
# Begründung: Die Base-Case-Routen zeigen das Verhalten VOR der Maßnahme.
# Diese Gruppe entspricht dem, was ohne Tempo-10 durch die Zone gefahren wäre.
affected_ids = {pid for pid, d in base_personen.items() if d['affected']}

n_gesamt   = len(base_personen)
n_affected = len(affected_ids)

print(f"\n  Ergebnis Block 1:")
print(f"  Gesamt simulierte Personen (1%-Sample): {n_gesamt:,}")
print(f"  Direkt betroffene Agenten:              {n_affected:,}")
print(f"  Anteil am Gesamtverkehr:                {n_affected/n_gesamt*100:.1f}%")
print(f"  Hochgerechnet (×{SAMPLE_FAKTOR}):                  {n_affected*SAMPLE_FAKTOR:,} Personen")


# =============================================================================
# BLOCK 2: UNTERGRUPPEN BILDEN
# =============================================================================
# Die betroffenen Agenten werden in drei Untergruppen eingeteilt:
#
#   Gruppe C – Anwohner:          home-Aktivität auf einem Changeset-Link
#   Gruppe B – Zielverkehr:       andere (non-home) Aktivität auf Changeset-Link
#   Gruppe A – Durchgangsverkehr: keine Aktivität auf Changeset-Link
#
# Grundlage: Aktivitäts-Links aus den Base-Case-Plans
# MATSim-interne Interaktionsaktivitäten (car interaction etc.) werden
# herausgefiltert, da sie keine echten Zielorte darstellen.
#
# Validierung: Summe A + B + C muss = Anzahl affected agents ergeben.
# =============================================================================

print("\n[Block 2] Bilde Untergruppen der betroffenen Agenten...")

gruppe_a = set()  # Durchgangsverkehr
gruppe_b = set()  # Zielverkehr (non-home Aktivität in Zone)
gruppe_c = set()  # Anwohner (home-Aktivität in Zone)

for pid in affected_ids:
    # Echte Aktivitäten filtern (ohne MATSim-interne Interaktionstypen)
    echte_akt = [
        (atyp, alink)
        for atyp, alink in base_personen[pid]['activities']
        if atyp not in INTERAKTION_TYPEN
    ]
    # Aktivitäten, die auf einem Changeset-Link stattfinden
    akt_in_zone = [(t, l) for t, l in echte_akt if l in affected_links]

    # Klassifikation: home > non-home > kein Ziel in Zone
    hat_home_in_zone  = any(t.startswith('home') for t, l in akt_in_zone)
    hat_andere_in_zone = any(not t.startswith('home') for t, l in akt_in_zone)

    if hat_home_in_zone:
        gruppe_c.add(pid)      # Anwohner
    elif hat_andere_in_zone:
        gruppe_b.add(pid)      # Zielverkehr
    else:
        gruppe_a.add(pid)      # Durchgangsverkehr

# --- Validierungscheck: Summe muss gleich Gesamtzahl affected agents sein ---
summe = len(gruppe_a) + len(gruppe_b) + len(gruppe_c)
assert summe == n_affected, (
    f"FEHLER: Gruppencheck fehlgeschlagen! "
    f"A({len(gruppe_a)}) + B({len(gruppe_b)}) + C({len(gruppe_c)}) "
    f"= {summe} ≠ {n_affected}"
)

print(f"\n  Ergebnis Block 2:")
print(f"  Gruppe A – Durchgangsverkehr: {len(gruppe_a):>4} Agenten ({len(gruppe_a)/n_affected*100:.1f}%)")
print(f"  Gruppe B – Zielverkehr:       {len(gruppe_b):>4} Agenten ({len(gruppe_b)/n_affected*100:.1f}%)")
print(f"  Gruppe C – Anwohner:          {len(gruppe_c):>4} Agenten ({len(gruppe_c)/n_affected*100:.1f}%)")
print(f"  Summen-Check: {len(gruppe_a)}+{len(gruppe_b)}+{len(gruppe_c)} = {summe} ✓")

# Gruppen-Zuordnung als Dictionary für späteren Zugriff
gruppen_label = {}
for pid in gruppe_a: gruppen_label[pid] = 'A_Durchgang'
for pid in gruppe_b: gruppen_label[pid] = 'B_Zielverkehr'
for pid in gruppe_c: gruppen_label[pid] = 'C_Anwohner'


# =============================================================================
# BLOCK 3: BASIC-ANALYSE
# =============================================================================
# Vergleich Base Case vs. Policy Case für alle affected agents (gesamt)
# und getrennt nach den drei Untergruppen.
#
# Analysierte Kennzahlen:
#   (a) Modal Split – Anzahl Trips pro Hauptmodus
#   (b) Number of Trips – Gesamtanzahl Trips
#   (c) Change in km travelled – Veränderung der Reisedistanz
#   (d) Change in time spent in traffic – Veränderung der Reisezeit
#
# Datenquelle: output_trips.csv (Base + Policy)
# Begründung: Die trips.csv liefert aggregierte Trip-Ebene mit main_mode,
#             traveled_distance und trav_time – direkt verwendbar ohne
#             die verschachtelte Legs-Struktur der Plans-Datei auflösen
#             zu müssen.
# =============================================================================

print("\n[Block 3] Basic-Analyse (Modal Split, Trips, Distanz, Reisezeit)...")

# --- Trips-Dateien laden ---
# Trennzeichen ist Semikolon (MATSim-Standard)
trips_base   = pd.read_csv(BASE_TRIPS,   sep=';')
trips_policy = pd.read_csv(POLICY_TRIPS, sep=';')

# Spalte "person" ist die Agenten-ID (als String für konsistenten Vergleich)
trips_base['person']   = trips_base['person'].astype(str)
trips_policy['person'] = trips_policy['person'].astype(str)

# Gruppen-Label zur Trips-Tabelle hinzufügen
trips_base['gruppe']   = trips_base['person'].map(gruppen_label)
trips_policy['gruppe'] = trips_policy['person'].map(gruppen_label)

# Nur affected agents behalten
base_aff   = trips_base  [trips_base  ['person'].isin(affected_ids)].copy()
policy_aff = trips_policy[trips_policy['person'].isin(affected_ids)].copy()

# Reisezeit: HH:MM:SS → Minuten umrechnen
def hms_zu_minuten(series):
    """Wandelt HH:MM:SS Strings in Minuten (float) um."""
    def parse(s):
        try:
            parts = str(s).split(':')
            return int(parts[0]) * 60 + int(parts[1]) + int(parts[2]) / 60
        except:
            return 0.0
    return series.apply(parse)

base_aff['trav_min']   = hms_zu_minuten(base_aff['trav_time'])
policy_aff['trav_min'] = hms_zu_minuten(policy_aff['trav_time'])

# Distanz: Meter → Kilometer
base_aff['dist_km']   = base_aff['traveled_distance']   / 1000
policy_aff['dist_km'] = policy_aff['traveled_distance'] / 1000

# --- Hilfsfunktion: Kennzahlen für eine Gruppe berechnen ---
def berechne_kennzahlen(df_base, df_policy, label):
    """
    Berechnet die vier Basis-Kennzahlen für eine Agentengruppe.
    Gibt ein Dictionary mit den Ergebnissen zurück.
    """
    n_agenten  = df_base['person'].nunique()
    n_trips_b  = len(df_base)
    n_trips_p  = len(df_policy)

    dist_b = df_base['dist_km'].sum()
    dist_p = df_policy['dist_km'].sum()

    zeit_b = df_base['trav_min'].sum()
    zeit_p = df_policy['trav_min'].sum()

    # Modal Split: Anzahl Trips je Hauptmodus
    modal_b = df_base['main_mode'].value_counts().to_dict()
    modal_p = df_policy['main_mode'].value_counts().to_dict()
    alle_modi = sorted(set(list(modal_b.keys()) + list(modal_p.keys())))

    return {
        'Gruppe':                label,
        'Anzahl_Agenten_Sample': n_agenten,
        'Anzahl_Agenten_Real':   n_agenten * SAMPLE_FAKTOR,
        'Trips_Base':            n_trips_b,
        'Trips_Policy':          n_trips_p,
        'Trips_Delta':           n_trips_p - n_trips_b,
        'Distanz_km_Base':       round(dist_b, 1),
        'Distanz_km_Policy':     round(dist_p, 1),
        'Distanz_km_Delta':      round(dist_p - dist_b, 1),
        'Distanz_km_Delta_Real': round((dist_p - dist_b) * SAMPLE_FAKTOR, 1),
        'Zeit_h_Base':           round(zeit_b / 60, 2),
        'Zeit_h_Policy':         round(zeit_p / 60, 2),
        'Zeit_h_Delta':          round((zeit_p - zeit_b) / 60, 3),
        'Zeit_h_Delta_Real':     round((zeit_p - zeit_b) / 60 * SAMPLE_FAKTOR, 1),
        **{f'Modal_Base_{m}':   modal_b.get(m, 0) for m in alle_modi},
        **{f'Modal_Policy_{m}': modal_p.get(m, 0) for m in alle_modi},
        **{f'Modal_Delta_{m}':  modal_p.get(m, 0) - modal_b.get(m, 0) for m in alle_modi},
    }

# --- Kennzahlen für Gesamt + alle drei Gruppen berechnen ---
ergebnisse = []

# Gesamt: alle affected agents
ergebnisse.append(berechne_kennzahlen(base_aff, policy_aff, 'GESAMT'))

# Gruppe A: Durchgangsverkehr
ergebnisse.append(berechne_kennzahlen(
    base_aff  [base_aff  ['gruppe'] == 'A_Durchgang'],
    policy_aff[policy_aff['gruppe'] == 'A_Durchgang'],
    'A_Durchgang'
))

# Gruppe B: Zielverkehr
ergebnisse.append(berechne_kennzahlen(
    base_aff  [base_aff  ['gruppe'] == 'B_Zielverkehr'],
    policy_aff[policy_aff['gruppe'] == 'B_Zielverkehr'],
    'B_Zielverkehr'
))

# Gruppe C: Anwohner
ergebnisse.append(berechne_kennzahlen(
    base_aff  [base_aff  ['gruppe'] == 'C_Anwohner'],
    policy_aff[policy_aff['gruppe'] == 'C_Anwohner'],
    'C_Anwohner'
))

df_ergebnisse = pd.DataFrame(ergebnisse)

# Ergebnisse speichern und ausgeben
pfad_basis = os.path.join(OUTPUT_DIR, 'block3_basic_analyse.csv')
df_ergebnisse.to_csv(pfad_basis, index=False, encoding='utf-8-sig', sep=';')

print(f"\n  Ergebnis Block 3 (Überblick):")
kern_spalten = [
    'Gruppe', 'Anzahl_Agenten_Sample',
    'Trips_Base', 'Trips_Policy', 'Trips_Delta',
    'Distanz_km_Base', 'Distanz_km_Policy', 'Distanz_km_Delta',
    'Zeit_h_Base', 'Zeit_h_Policy', 'Zeit_h_Delta'
]
print(df_ergebnisse[kern_spalten].to_string(index=False))
print(f"\n  Vollständige Tabelle gespeichert: {pfad_basis}")

# Separate Modal-Split-Tabelle für bessere Lesbarkeit
modal_spalten = ['Gruppe'] + [s for s in df_ergebnisse.columns if 'Modal_' in s]
df_modal = df_ergebnisse[modal_spalten]
pfad_modal = os.path.join(OUTPUT_DIR, 'block3_modal_split.csv')
df_modal.to_csv(pfad_modal, index=False, encoding='utf-8-sig', sep=';')
print(f"  Modal-Split-Tabelle gespeichert:  {pfad_modal}")


# =============================================================================
# BLOCK 4: DEEP DIVE – WER BLEIBT, WER GEHT?
# =============================================================================
# Frage: Wie viele der betroffenen Agenten im Base Case fahren im Policy Case
#        noch durch die Tempo-10-Zone? Und was charakterisiert sie?
#
# Vorgehen:
#   1. Aus den Policy-Plans: Identifiziere, wer im Policy Case noch einen
#      motorisierten Leg durch einen Changeset-Link hat (= "Bleiber").
#   2. Vergleiche mit den Base-Case-Betroffenen → drei Gruppen:
#      - Bleiber:    im Base Case UND im Policy Case in der Zone
#      - Verlasser:  im Base Case in der Zone, aber nicht mehr im Policy Case
#      - Neuzugänge: nicht im Base Case, aber im Policy Case in der Zone
#   3. Analysiere Bleiber nach Untergruppe (A/B/C) und Modus
#   4. Score-Delta der Bleiber vs. Verlasser
#
# Datenquelle: beide experienced_plans XML
# =============================================================================

print("\n[Block 4] Deep Dive – Wer bleibt, wer geht?...")

# --- 4a: Affected agents im Policy Case identifizieren ---
# Gleiche Methodik wie Block 1, aber mit Policy-Plans
policy_affected_ids = {
    pid for pid, d in policy_personen.items() if d['affected']
}

# Mengenoperationen
bleiber    = affected_ids & policy_affected_ids   # Base UND Policy
verlasser  = affected_ids - policy_affected_ids   # nur Base
neuzugaenge = policy_affected_ids - affected_ids  # nur Policy

print(f"\n  Ergebnis Block 4a – Zonendurchfahrten im Vergleich:")
print(f"  Affected agents Base Case:            {len(affected_ids):>4}")
print(f"  Affected agents Policy Case:          {len(policy_affected_ids):>4}")
print(f"")
print(f"  Bleiber (Base UND Policy in Zone):    {len(bleiber):>4} ({len(bleiber)/len(affected_ids)*100:.1f}% der Base-Gruppe)")
print(f"  Verlasser (nur Base in Zone):         {len(verlasser):>4} ({len(verlasser)/len(affected_ids)*100:.1f}%)")
print(f"  Neuzugänge (nur Policy in Zone):      {len(neuzugaenge):>4}")

# --- 4b: Bleiber nach Untergruppe aufschlüsseln ---
bleiber_nach_gruppe = {
    'A_Durchgang':   len(bleiber & gruppe_a),
    'B_Zielverkehr': len(bleiber & gruppe_b),
    'C_Anwohner':    len(bleiber & gruppe_c),
}
verlasser_nach_gruppe = {
    'A_Durchgang':   len(verlasser & gruppe_a),
    'B_Zielverkehr': len(verlasser & gruppe_b),
    'C_Anwohner':    len(verlasser & gruppe_c),
}

print(f"\n  Bleiber nach Untergruppe:")
for gr, n in bleiber_nach_gruppe.items():
    gr_gesamt = len(gruppe_a) if 'Durch' in gr else (len(gruppe_b) if 'Ziel' in gr else len(gruppe_c))
    print(f"    {gr:20s}: {n:>3} von {gr_gesamt:>3} ({n/gr_gesamt*100:.1f}% bleiben)")

print(f"\n  Verlasser nach Untergruppe:")
for gr, n in verlasser_nach_gruppe.items():
    gr_gesamt = len(gruppe_a) if 'Durch' in gr else (len(gruppe_b) if 'Ziel' in gr else len(gruppe_c))
    print(f"    {gr:20s}: {n:>3} von {gr_gesamt:>3} ({n/gr_gesamt*100:.1f}% verlassen Zone)")

# --- 4c: Modal Split der Bleiber (Policy Case) ---
# Welche Verkehrsmittel nutzen die Bleiber noch in der Zone?
bleiber_trips_policy = trips_policy[trips_policy['person'].isin(bleiber)]
bleiber_trips_base   = trips_base  [trips_base  ['person'].isin(bleiber)]

modal_bleiber_base   = bleiber_trips_base['main_mode'].value_counts()
modal_bleiber_policy = bleiber_trips_policy['main_mode'].value_counts()

print(f"\n  Modal Split der Bleiber:")
print(f"  {'Modus':<15} {'Base':>8} {'Policy':>8} {'Delta':>8}")
alle_modi_bleiber = sorted(set(list(modal_bleiber_base.index) + list(modal_bleiber_policy.index)))
for m in alle_modi_bleiber:
    b = modal_bleiber_base.get(m, 0)
    p = modal_bleiber_policy.get(m, 0)
    print(f"  {m:<15} {b:>8} {p:>8} {p-b:>+8}")

# --- 4d: Score-Delta – Wer wird stärker belastet? ---
# Score-Delta = Policy-Score minus Base-Score pro Person
# Negativer Wert = Wohlfahrtsverlust durch die Maßnahme

def score_delta(pid):
    """Berechnet das Score-Delta (Policy - Base) für eine Person."""
    sb = base_personen.get(pid, {}).get('score')
    sp = policy_personen.get(pid, {}).get('score')
    if sb is not None and sp is not None:
        return sp - sb
    return None

bleiber_scores   = {pid: score_delta(pid) for pid in bleiber   if score_delta(pid) is not None}
verlasser_scores = {pid: score_delta(pid) for pid in verlasser if score_delta(pid) is not None}

bleiber_delta_werte   = list(bleiber_scores.values())
verlasser_delta_werte = list(verlasser_scores.values())

import statistics
def zusammenfassung(werte, label):
    if not werte: return
    print(f"  {label}:")
    print(f"    Mittelwert:              {statistics.mean(werte):>+7.3f}")
    print(f"    Median:                  {statistics.median(werte):>+7.3f}")
    print(f"    Verschlechtert (delta<0):{sum(1 for v in werte if v<0):>4} von {len(werte)} ({sum(1 for v in werte if v<0)/len(werte)*100:.1f}%)")
    print(f"    Verbessert (delta>0):   {sum(1 for v in werte if v>0):>4} von {len(werte)} ({sum(1 for v in werte if v>0)/len(werte)*100:.1f}%)")

print(f"\n  Score-Delta (Policy − Base):")
zusammenfassung(bleiber_delta_werte,   "Bleiber")
zusammenfassung(verlasser_delta_werte, "Verlasser")

# --- 4e: Ergebnistabellen erstellen und speichern ---

# Tabelle: Übersicht Bleiber / Verlasser / Neuzugänge nach Gruppe
rows_vergleich = []
for gr_name, gr_set in [('A_Durchgang', gruppe_a), ('B_Zielverkehr', gruppe_b), ('C_Anwohner', gruppe_c)]:
    gr_bleiber    = bleiber    & gr_set
    gr_verlasser  = verlasser  & gr_set
    gr_neuzugaenge = neuzugaenge   # keine Gruppenzuordnung für Neuzugänge
    rows_vergleich.append({
        'Gruppe':              gr_name,
        'Basis_Gesamt':        len(gr_set),
        'Bleiber_n':           len(gr_bleiber),
        'Bleiber_pct':         round(len(gr_bleiber)/len(gr_set)*100, 1) if gr_set else 0,
        'Verlasser_n':         len(gr_verlasser),
        'Verlasser_pct':       round(len(gr_verlasser)/len(gr_set)*100, 1) if gr_set else 0,
    })
rows_vergleich.append({
    'Gruppe':              'GESAMT',
    'Basis_Gesamt':        n_affected,
    'Bleiber_n':           len(bleiber),
    'Bleiber_pct':         round(len(bleiber)/n_affected*100, 1),
    'Verlasser_n':         len(verlasser),
    'Verlasser_pct':       round(len(verlasser)/n_affected*100, 1),
})
df_vergleich = pd.DataFrame(rows_vergleich)
pfad_vergleich = os.path.join(OUTPUT_DIR, 'block4_bleiber_verlasser.csv')
df_vergleich.to_csv(pfad_vergleich, index=False, encoding='utf-8-sig', sep=';')

# Tabelle: Modal Split der Bleiber
rows_modal = []
for m in alle_modi_bleiber:
    rows_modal.append({
        'Modus':         m,
        'Base_Trips':    int(modal_bleiber_base.get(m, 0)),
        'Policy_Trips':  int(modal_bleiber_policy.get(m, 0)),
        'Delta_Trips':   int(modal_bleiber_policy.get(m, 0)) - int(modal_bleiber_base.get(m, 0)),
    })
df_modal_bleiber = pd.DataFrame(rows_modal)
pfad_modal_b = os.path.join(OUTPUT_DIR, 'block4_modal_bleiber.csv')
df_modal_bleiber.to_csv(pfad_modal_b, index=False, encoding='utf-8-sig', sep=';')

# Tabelle: Score-Deltas pro Person mit Gruppen-Label
rows_score = []
for pid in bleiber | verlasser:
    delta = score_delta(pid)
    if delta is not None:
        rows_score.append({
            'person_id': pid,
            'gruppe':    gruppen_label.get(pid, 'unbekannt'),
            'status':    'Bleiber' if pid in bleiber else 'Verlasser',
            'score_base':   round(base_personen[pid].get('score') or 0, 3),
            'score_policy': round(policy_personen.get(pid, {}).get('score') or 0, 3),
            'score_delta':  round(delta, 3),
        })
df_scores = pd.DataFrame(rows_score)
pfad_scores = os.path.join(OUTPUT_DIR, 'block4_score_delta.csv')
df_scores.to_csv(pfad_scores, index=False, encoding='utf-8-sig', sep=';')

# Neuzugänge auch erfassen
neuzug_data = {'Anzahl_Neuzugaenge_Sample': len(neuzugaenge),
               'Anzahl_Neuzugaenge_Real': len(neuzugaenge)*SAMPLE_FAKTOR}
df_nz = pd.DataFrame([neuzug_data])
pfad_nz = os.path.join(OUTPUT_DIR, 'block4_neuzugaenge.csv')
df_nz.to_csv(pfad_nz, index=False, encoding='utf-8-sig', sep=';')

print(f"\n  Tabellen gespeichert:")
print(f"    {pfad_vergleich}")
print(f"    {pfad_modal_b}")
print(f"    {pfad_scores}")
print(f"    {pfad_nz}")


# =============================================================================
# ABSCHLIESSENDE ZUSAMMENFASSUNG
# =============================================================================

print("\n" + "=" * 65)
print("ZUSAMMENFASSUNG (Hochrechnung ×100 für Realwelt)")
print("=" * 65)
print(f"  Simulierte Personen (1%-Sample):       {n_gesamt:>6,}")
print(f"  Direkt betroffene Agenten (Sample):    {n_affected:>6,}")
print(f"  Direkt betroffene Agenten (Real):      {n_affected*SAMPLE_FAKTOR:>6,}")
print(f"  Anteil Gesamtverkehr:                  {n_affected/n_gesamt*100:>6.1f}%")
print()
print(f"  Untergruppen:")
print(f"    A – Durchgangsverkehr:  {len(gruppe_a):>3} ({len(gruppe_a)/n_affected*100:.1f}%)")
print(f"    B – Zielverkehr:        {len(gruppe_b):>3} ({len(gruppe_b)/n_affected*100:.1f}%)")
print(f"    C – Anwohner:           {len(gruppe_c):>3} ({len(gruppe_c)/n_affected*100:.1f}%)")
print()
row_ges = df_ergebnisse[df_ergebnisse['Gruppe'] == 'GESAMT'].iloc[0]
print(f"  Distanz-Delta (Sample):  {row_ges['Distanz_km_Delta']:>+8.1f} km")
print(f"  Distanz-Delta (Real):    {row_ges['Distanz_km_Delta_Real']:>+8.1f} km")
print(f"  Zeit-Delta (Sample):     {row_ges['Zeit_h_Delta']:>+8.3f} h")
print(f"  Zeit-Delta (Real):       {row_ges['Zeit_h_Delta_Real']:>+8.1f} h")
print()
print(f"  Bleiber in Zone:  {len(bleiber):>3} ({len(bleiber)/n_affected*100:.1f}% der Base-Gruppe)")
print(f"  Verlasser Zone:   {len(verlasser):>3} ({len(verlasser)/n_affected*100:.1f}%)")
print(f"  Neuzugänge Zone:  {len(neuzugaenge):>3}")
print()
print(f"  Alle Ergebnistabellen in: {OUTPUT_DIR}/")
print("=" * 65)
