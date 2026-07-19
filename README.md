# stemma

`inventory.yaml`과 장비별 Syncthing snapshot을 안전하게 읽어 immutable domain model로
변환하는 Python package입니다.

PR1의 schema, loader, path normalization 및 domain model, PR2의 로컬 Syncthing
snapshot exporter, PR3의 desired/actual reconciliation과 deterministic Catalog JSON
serializer를 함께 제공합니다.

PR2의 로컬 exporter는 Syncthing 1.12.0 이상을 대상으로 하며, 읽기 전용 REST API로
민감정보가 제거된 `device-inventory.json`을 생성합니다. `SYNCTHING_API_KEY` 환경변수를
별도로 설정한 후 다음처럼 실행합니다.

```bash
uv run docs-sync-exporter snapshot --output device-inventory.json
```

기본 endpoint는 `http://127.0.0.1:8384`입니다. 원격 endpoint는 HTTPS만 허용하며
필요하면 `--ca-bundle`로 신뢰할 CA bundle을 지정합니다.

Catalog는 다음 public interface로 생성하고 직렬화할 수 있습니다.

```python
from pathlib import Path

from stemma import build_catalog, serialize_catalog

catalog = build_catalog(Path("inventory.yaml"), [Path("device-inventory.json")])
catalog_json = serialize_catalog(catalog)
```

PR4의 local read-only viewer는 operator가 현재 host에 미리 준비한 inventory와
snapshot만 표시합니다. 중앙 snapshot 수집이나 장비 간 전송은 하지 않으며,
인증이 없는 v0.0.1 server는 `127.0.0.1`에만 bind할 수 있습니다.

```bash
uv run docs-sync-catalog web \
  --inventory ./inventory.yaml \
  --snapshot ./device-inventory-a.json \
  --snapshot ./device-inventory-b.json
```

실행 후 `http://127.0.0.1:8080/catalog`에서 folder/device별 desired/actual path와
mode, `missing`/`path_mismatch`/`mode_mismatch` drift 및 filter를 확인할 수 있습니다.

## 개발 환경

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv run pyright
```
