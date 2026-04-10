from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
import sys

from dotenv import load_dotenv

from rfp_scraper.config import load_config
from rfp_scraper.pipeline import RFPPipeline, run_pipeline_sync


def non_negative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return number


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search and crawl 401k/403b/457 RFP pages and PDFs.")
    parser.add_argument(
        "--config",
        default="config/queries.yaml",
        help="Path to the YAML config file.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run searches and crawl result URLs.")
    run_parser.add_argument(
        "--config",
        dest="command_config",
        default=None,
        help="Path to the YAML config file.",
    )
    run_parser.add_argument(
        "--query-limit",
        type=non_negative_int,
        default=None,
        help="Limit the number of configured queries.",
    )
    run_parser.add_argument(
        "--search-results",
        type=positive_int,
        default=None,
        help="Number of Serper results to request per query.",
    )
    run_parser.add_argument(
        "--crawl-limit",
        type=non_negative_int,
        default=None,
        help="Limit the number of unique URLs crawled.",
    )
    run_parser.add_argument("--skip-search", action="store_true", help="Do not call Serper; crawl only source URLs.")
    run_parser.add_argument(
        "--skip-source-urls",
        action="store_true",
        help="Do not crawl configured source URLs; use only search results.",
    )

    show_parser = subparsers.add_parser("show-config", help="Print the resolved config.")
    show_parser.add_argument(
        "--config",
        dest="command_config",
        default=None,
        help="Path to the YAML config file.",
    )
    return parser


def main() -> None:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()

    config_path = args.command_config or args.config
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        parser.error(f"Config file not found: {config_path}")
        sys.exit(2)
    except (ValueError, TypeError) as exc:
        parser.error(f"Invalid config: {exc}")
        sys.exit(2)
    if args.command == "show-config":
        print(json.dumps({
            "search": asdict(config.search),
            "crawl": asdict(config.crawl),
            "source_urls": config.source_urls,
        }, indent=2))
        return

    root_dir = Path(__file__).resolve().parent
    pipeline = RFPPipeline(config=config, root_dir=root_dir)
    records = run_pipeline_sync(
        pipeline,
        query_limit=args.query_limit,
        search_results=args.search_results,
        crawl_limit=args.crawl_limit,
        skip_search=args.skip_search,
        skip_source_urls=args.skip_source_urls,
    )
    print(f"Wrote {len(records)} candidate records under {root_dir / 'data'}")


if __name__ == "__main__":
    main()