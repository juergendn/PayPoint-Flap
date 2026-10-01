from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.templating import Jinja2Templates

# Anzeige immer in deutscher Ortszeit – unabhängig von der Zeitzone des
# Containers (Entwicklung: UTC).
ORTSZEIT = ZoneInfo("Europe/Berlin")

templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


def ortszeit(wert: datetime | None, format: str = "%d.%m.%Y %H:%M") -> str:
    return wert.astimezone(ORTSZEIT).strftime(format) if wert else ""


templates.env.filters["ortszeit"] = ortszeit
