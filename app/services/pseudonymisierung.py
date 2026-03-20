"""
DSGVO-konforme Pseudonymisierung für KI-Anfragen.
Ersetzt personenbezogene Daten durch Pseudonyme (MA_001 etc.)
bevor Daten an externe KI-Services gesendet werden.
"""
import re


class Pseudonymisierer:
    """Bidirektionale Pseudonymisierung für Mitarbeiterdaten"""

    def __init__(self, mitarbeiter_liste):
        self._id_zu_pseudo = {}
        self._pseudo_zu_id = {}
        self._name_zu_pseudo = {}

        for i, ma in enumerate(mitarbeiter_liste, 1):
            pseudo = f'MA_{i:03d}'
            self._id_zu_pseudo[ma.id] = pseudo
            self._pseudo_zu_id[pseudo] = ma.id
            self._name_zu_pseudo[ma.name] = pseudo

    def pseudonymisiere_mitarbeiter(self, mitarbeiter_liste):
        """Erzeugt pseudonymisierte Mitarbeiter-Dicts ohne PII"""
        result = []
        for ma in mitarbeiter_liste:
            pseudo = self._id_zu_pseudo.get(ma.id, f'MA_UNKNOWN_{ma.id}')
            quals = [mq.qualifikation.name for mq in ma.qualifikationen] if ma.qualifikationen else []
            result.append({
                'pseudo_name': pseudo,
                'stellenanteil': ma.stellenanteil,
                'arbeitsstunden_woche': ma.arbeitsstunden_woche,
                'qualifikationen': quals,
                'regel_ausnahmen': ma.regel_ausnahmen or {},
            })
        return result

    def pseudonymisiere_konflikte(self, konflikte):
        """Pseudonymisiert Konflikt-Objekte"""
        result = []
        for k in konflikte:
            k_dict = dict(k) if isinstance(k, dict) else {
                'typ': k.get('typ', ''),
                'beschreibung': k.get('beschreibung', ''),
                'schwere': k.get('schwere', ''),
                'datum': str(k.get('datum', '')),
                'mitarbeiter': k.get('mitarbeiter', ''),
                'details': k.get('details', ''),
            }
            # Pseudonymisiere Mitarbeiternamen in allen Textfeldern
            for feld in ['beschreibung', 'mitarbeiter', 'details']:
                if k_dict.get(feld):
                    k_dict[feld] = self.pseudonymisiere_text(str(k_dict[feld]))
            result.append(k_dict)
        return result

    def pseudonymisiere_text(self, text):
        """Ersetzt alle echten Mitarbeiternamen durch Pseudonyme"""
        if not text:
            return text
        # Sortiere nach Namenslänge (längste zuerst) um Teilmatches zu vermeiden
        for name in sorted(self._name_zu_pseudo, key=len, reverse=True):
            text = text.replace(name, self._name_zu_pseudo[name])
        return text

    def depseudonymisiere_text(self, text):
        """Ersetzt Pseudonyme (MA_001 etc.) durch echte Namen für Anzeige"""
        if not text:
            return text

        def ersetze(match):
            pseudo = match.group(0)
            ma_id = self._pseudo_zu_id.get(pseudo)
            if ma_id is not None:
                # Finde echten Namen aus dem Reverse-Mapping
                for name, p in self._name_zu_pseudo.items():
                    if p == pseudo:
                        return name
            return pseudo

        return re.sub(r'MA_\d{3}', ersetze, text)

    def get_pseudo_fuer_id(self, mitarbeiter_id):
        """Gibt Pseudonym für eine Mitarbeiter-ID zurück"""
        return self._id_zu_pseudo.get(mitarbeiter_id)

    def get_id_fuer_pseudo(self, pseudo):
        """Gibt Mitarbeiter-ID für ein Pseudonym zurück"""
        return self._pseudo_zu_id.get(pseudo)
