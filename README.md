# stemma

`inventory.yaml`과 장비별 Syncthing snapshot을 안전하게 읽어 immutable domain model로
변환하는 Python package입니다.

PR1 범위는 schema, loader, path normalization 및 reconciliation 결과 model까지입니다.
Syncthing API 수집과 desired/actual reconciliation은 후속 PR에서 구현합니다.

PR2의 로컬 exporter는 Syncthing 1.12.0 이상을 대상으로 하며, 읽기 전용 REST API로
민감정보가 제거된 `device-inventory.json`을 생성합니다. `SYNCTHING_API_KEY` 환경변수를
별도로 설정한 후 다음처럼 실행합니다.

```bash
uv run docs-sync-exporter snapshot --output device-inventory.json
```

기본 endpoint는 `http://127.0.0.1:8384`입니다. 원격 endpoint는 HTTPS만 허용하며
필요하면 `--ca-bundle`로 신뢰할 CA bundle을 지정합니다.

## 개발 환경

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv run pyright
```
