PYTHON ?= python3
TARGET ?= 10000

.PHONY: test verify build

test:
	$(PYTHON) -m unittest discover -s tests -v
	$(PYTHON) -m py_compile scripts/*.py

build:
	@test -n "$(PDMX_CSV)" || (echo 'Set PDMX_CSV=/path/to/PDMX.csv' >&2; exit 2)
	$(PYTHON) scripts/build_manifest.py --input "$(PDMX_CSV)" --output-dir data --target $(TARGET)

verify:
	$(PYTHON) scripts/verify_manifest.py --catalog data/orchestra_exact_$(TARGET).csv --stats data/stats.json --target $(TARGET)
