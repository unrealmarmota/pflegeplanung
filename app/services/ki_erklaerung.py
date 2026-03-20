"""
KI-gestützte Erklärungen für Dienstplan-Ergebnisse.
Verwendet Claude API mit DSGVO-konformer Pseudonymisierung.
"""
import os
import logging
from datetime import date
from calendar import monthrange

logger = logging.getLogger(__name__)

# Verfügbare Modelle
MODELLE = {
    'haiku': 'claude-haiku-4-5-20251001',
    'sonnet': 'claude-sonnet-4-6',
    'opus': 'claude-opus-4-6',
}

SYSTEM_PROMPT = """Du bist ein Experte für Dienstplanung in der Pflege. \
Du analysierst automatisch generierte Dienstpläne und erklärst Entscheidungen \
verständlich für die Pflegedienstleitung. Antworte auf Deutsch, knapp und praxisnah. \
Verwende die Mitarbeiter-Kennungen (MA_001 etc.) wie angegeben. \
Strukturiere deine Antwort mit kurzen Absätzen und Aufzählungen."""


class KIErklaerung:
    """KI-Erklärungsservice für Dienstplanungen"""

    def __init__(self):
        self._api_key = self._lade_api_key()
        self._modell = self._lade_modell()
        self._cache = {}

    def _lade_api_key(self):
        """Lädt API-Key: DB-Einstellung > Env-Var"""
        try:
            from app.models import Einstellungen
            key = Einstellungen.get('claude_api_key')
            if key:
                return key
        except Exception:
            pass
        return os.environ.get('CLAUDE_API_KEY', '')

    def _lade_modell(self):
        """Lädt Modell-ID aus Einstellungen"""
        try:
            from app.models import Einstellungen
            modell_key = Einstellungen.get('claude_modell', 'haiku')
            return MODELLE.get(modell_key, MODELLE['haiku'])
        except Exception:
            return MODELLE['haiku']

    def ist_verfuegbar(self):
        """Prüft ob KI-Erklärungen verfügbar sind"""
        if not self._api_key:
            return False
        try:
            from app.models import Einstellungen
            aktiv = Einstellungen.get('ki_erklaerung_aktiv', 'true')
            return aktiv.lower() in ('true', '1', 'ja')
        except Exception:
            return bool(self._api_key)

    def erklaere_plan(self, result, mitarbeiter_pseudonym, regeln, jahr, monat):
        """Use Case A: Erkläre einen erfolgreichen Plan"""
        cache_key = ('plan', jahr, monat)
        if cache_key in self._cache:
            return self._cache[cache_key]

        ob = result.get('objective_breakdown', {})
        prompt = f"""Dienstplan für {monat:02d}/{jahr} wurde erfolgreich erstellt.

Eckdaten:
- Solver-Status: {ob.get('solver_status', 'unbekannt')}
- {ob.get('total_schichten', '?')} Schichten insgesamt geplant
- Objective-Wert: {ob.get('objective_wert', '?')}

Aktive Regeln:
{self._formatiere_regeln(regeln)}

Mitarbeiter ({len(mitarbeiter_pseudonym)}):
{self._formatiere_mitarbeiter(mitarbeiter_pseudonym)}

Wunschbilanz:
- Frei-Wünsche verletzt: {ob.get('frei_wuensche_verletzt', '?')}
- Dienst-Wünsche erfüllt: {ob.get('dienst_wuensche_erfuellt', '?')}
- Validierungsfehler: {ob.get('validierungsfehler', 0)}

Erkläre kurz: Warum sieht der Plan so aus? Welche Kompromisse wurden gemacht?"""

        antwort = self._rufe_api(prompt)
        if antwort['erfolg']:
            self._cache[cache_key] = antwort
        return antwort

    def erklaere_fehlschlag(self, result, mitarbeiter_pseudonym, regeln, jahr, monat):
        """Use Case B: Erkläre warum der Plan INFEASIBLE ist"""
        cache_key = ('fehlschlag', jahr, monat)
        if cache_key in self._cache:
            return self._cache[cache_key]

        diagnose = result.get('diagnose', [])
        diagnose_text = '\n'.join(
            f"- [{d.get('schwere', '?')}] {d.get('text', d.get('nachricht', '?'))}"
            for d in diagnose
        ) if diagnose else '- Keine spezifischen Diagnosen'

        prompt = f"""Planung für {monat:02d}/{jahr} ist FEHLGESCHLAGEN (keine gültige Lösung).

Diagnose-Probleme:
{diagnose_text}

Aktive Regeln:
{self._formatiere_regeln(regeln)}

Ressourcen:
- {len(mitarbeiter_pseudonym)} aktive Mitarbeiter
{self._formatiere_mitarbeiter(mitarbeiter_pseudonym)}

Fehler: {result.get('fehler', 'Unbekannt')}

Erkläre: Warum konnte kein Plan erstellt werden? Welche Regeln stehen im Konflikt? Was könnte man ändern?"""

        antwort = self._rufe_api(prompt)
        if antwort['erfolg']:
            self._cache[cache_key] = antwort
        return antwort

    def erklaere_konflikte(self, konflikte_pseudonym, regeln, jahr, monat):
        """Use Case C: Erkläre Konflikte"""
        cache_key = ('konflikte', jahr, monat)
        if cache_key in self._cache:
            return self._cache[cache_key]

        konflikte_text = '\n'.join(
            f"- [{k.get('schwere', '?')}] {k.get('typ', '?')}: {k.get('beschreibung', '?')}"
            + (f" (Mitarbeiter: {k['mitarbeiter']})" if k.get('mitarbeiter') else '')
            + (f" am {k['datum']}" if k.get('datum') else '')
            for k in konflikte_pseudonym
        ) if konflikte_pseudonym else '- Keine Konflikte'

        prompt = f"""Konflikte im Dienstplan {monat:02d}/{jahr}:

{konflikte_text}

Aktive Regeln:
{self._formatiere_regeln(regeln)}

Erkläre die Konflikte verständlich und schlage konkrete Lösungen vor."""

        antwort = self._rufe_api(prompt)
        if antwort['erfolg']:
            self._cache[cache_key] = antwort
        return antwort

    def bewerte_fairness(self, verteilung_pseudonym, regeln, jahr, monat):
        """Use Case D: Bewerte Fairness der Verteilung"""
        cache_key = ('fairness', jahr, monat)
        if cache_key in self._cache:
            return self._cache[cache_key]

        prompt = f"""Verteilung im Dienstplan {monat:02d}/{jahr}:

{verteilung_pseudonym}

Aktive Regeln:
{self._formatiere_regeln(regeln)}

Bewerte die Fairness der Verteilung. Gibt es Ungleichgewichte bei Nacht- oder Wochenenddiensten?"""

        antwort = self._rufe_api(prompt)
        if antwort['erfolg']:
            self._cache[cache_key] = antwort
        return antwort

    def invalidiere_cache(self, jahr=None, monat=None):
        """Löscht Cache (z.B. nach neuer Plangenerierung)"""
        if jahr and monat:
            self._cache = {
                k: v for k, v in self._cache.items()
                if k[1] != jahr or k[2] != monat
            }
        else:
            self._cache.clear()

    def _rufe_api(self, user_prompt):
        """Ruft die Claude API auf"""
        try:
            import anthropic
        except ImportError:
            return {
                'erfolg': False,
                'erklaerung': '',
                'fehler': 'anthropic-Paket nicht installiert. Bitte "pip install anthropic" ausführen.',
            }

        if not self._api_key:
            return {
                'erfolg': False,
                'erklaerung': '',
                'fehler': 'Kein API-Key konfiguriert. Bitte in Einstellungen hinterlegen.',
            }

        try:
            client = anthropic.Anthropic(api_key=self._api_key)
            response = client.messages.create(
                model=self._modell,
                max_tokens=800,
                system=SYSTEM_PROMPT,
                messages=[{'role': 'user', 'content': user_prompt}],
            )

            text = response.content[0].text
            tokens = response.usage.input_tokens + response.usage.output_tokens

            logger.info(f"KI-Erklärung generiert ({tokens} Tokens, Modell: {self._modell})")

            return {
                'erfolg': True,
                'erklaerung': text,
                'fehler': None,
                'tokens_verwendet': tokens,
                'modell': self._modell,
            }

        except anthropic.AuthenticationError:
            return {
                'erfolg': False,
                'erklaerung': '',
                'fehler': 'Ungültiger API-Key. Bitte in Einstellungen prüfen.',
            }
        except anthropic.RateLimitError:
            return {
                'erfolg': False,
                'erklaerung': '',
                'fehler': 'API-Ratenlimit erreicht. Bitte später erneut versuchen.',
            }
        except Exception as e:
            logger.error(f"KI-API-Fehler: {e}")
            return {
                'erfolg': False,
                'erklaerung': '',
                'fehler': f'KI-Service nicht erreichbar: {str(e)}',
            }

    def _formatiere_regeln(self, regeln):
        """Formatiert Regeln für den Prompt"""
        if not regeln:
            return '- Keine aktiven Regeln'
        lines = []
        for r in regeln:
            prio = 'hart' if r.prioritaet == 1 else 'weich'
            lines.append(f'- {r.name} ({prio})')
        return '\n'.join(lines)

    def _formatiere_mitarbeiter(self, mitarbeiter_pseudonym):
        """Formatiert pseudonymisierte Mitarbeiter für den Prompt"""
        lines = []
        for ma in mitarbeiter_pseudonym[:20]:  # Max 20 um Token zu sparen
            quals = ', '.join(ma.get('qualifikationen', [])) or 'keine'
            lines.append(
                f"- {ma['pseudo_name']}: {ma['stellenanteil']}% Stelle, "
                f"{ma.get('arbeitsstunden_woche', '?')}h/Woche, Qualifikationen: {quals}"
            )
        if len(mitarbeiter_pseudonym) > 20:
            lines.append(f'- ... und {len(mitarbeiter_pseudonym) - 20} weitere')
        return '\n'.join(lines)
