# MVT-Klappenautomat (PayPoint-Flap)

Klappenautomat mit 20 Fächern zur Ausgabe von Mitarbeiterbekleidung – MinervaTec eGbR.

Einstieg: [CLAUDE.md](CLAUDE.md) → [wiki/](wiki/) → [memory.md](memory.md)

## Schnellstart (ohne Hardware)

```sh
docker compose up --build
```

- Display: http://localhost:8000/
- Admin: http://localhost:8000/admin
- Hardware-Simulator: http://localhost:8081/

Tests: `docker compose run --rm app pytest`
