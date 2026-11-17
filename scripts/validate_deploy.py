"""Validate render.yaml against Render's current public Blueprint JSON Schema."""

import json
from pathlib import Path
from urllib.request import urlopen

import jsonschema
import yaml


def main():
    root = Path(__file__).resolve().parents[1]
    schema_url = "https://render.com/schema/render.yaml.json"
    with urlopen(schema_url, timeout=30) as response:
        schema = json.load(response)
    document = yaml.safe_load((root / "render.yaml").read_text(encoding="utf-8"))
    jsonschema.validators.validator_for(schema)(schema).validate(document)
    print("PASS render.yaml matches " + schema_url)


if __name__ == "__main__":
    main()
