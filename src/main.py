import argparse
import csv
import re
import shutil
from pathlib import Path
from typing import NamedTuple, Optional, Self


class SubtitleLocaleFixer:

    SUFFIXES = ('.ass', '.ssa', '.sup', '.srt')

    class Rule(NamedTuple):
        source: str
        target: str
        case_sensitive: bool

        @classmethod
        def from_csv(cls, path: Path) -> list[Self]:
            rules = []
            with Path(path).open(encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    rules.append(cls(
                        source=row["source"],
                        target=row["target"],
                        case_sensitive=row.get(
                            "is_case_sensitive", "false").lower() == "true"
                    ))

    def __init__(self, rules: list[Rule] = None, default_locale: Optional[str] = None):
        self.rules: list[SubtitleLocaleFixer.Rule] = rules or []
        self.default_locale: Optional[str] = default_locale

    def fix_name(self, filename: str) -> str:
        parts = filename.rsplit(".", 2)

        if len(parts) == 3:
            name, lang, ext = parts
        elif len(parts) == 2:
            name, ext = parts
            lang = None
        else:
            return filename

        if lang:
            for src, tgt, case_sensitive in self.rules:
                if ((case_sensitive and lang == src)
                        or (not case_sensitive and lang.lower() == src.lower())):
                    return f"{name}.{tgt}.{ext}"

        if self.default_locale and lang is None:
            return f"{name}.{self.default_locale}.{ext}"
        return filename


class MediaOrganizer:
    def __init__(self, target: Path, sub_fixer: SubtitleLocaleFixer):
        self.target = target.resolve()
        self.sub_fixer = sub_fixer

    def process_interactive(self):
        for item in sorted(self.target.iterdir()):
            if not item.is_dir():
                continue
            print(f"\nDirectory: {item.name}")
            season_input = input(
                "Season number (number / s=skip / q=quit): ").strip().lower()

            if season_input == "q":
                break
            if season_input == "s":
                continue

            self.organize_directory(season=season_input, directory=item)

    def organize_directory(self, season: str, directory: Path = None):
        if not directory:
            directory = self.target

        dir_season = directory.joinpath(f"Season {season}")
        dir_extra = directory.joinpath("EXTRA", f"Season {season}")

        dir_season.mkdir(exist_ok=True)
        dir_extra.mkdir(exist_ok=True)

        for f in [p for p in directory.iterdir()
                  if p.is_file() and p.suffix in self.sub_fixer.SUFFIXES]:
            shutil.move(f, self.sub_fixer.fix_name(f.name))

        for d in [p for p in directory.iterdir() if p.is_dir()]:
            shutil.move(d, dir_extra)

        # for f in [p for p in directory.iterdir() if p.is_file()]:
        #     search = re.search(r'\[\d{1,2}\]|\s\d{2}(?=\s|$)|S\d+E\d+', f.name)
        #     if not search:
        #         pass

        for f in [p for p in directory.iterdir() if p.is_file()]:
            shutil.move(d,  dir_season)


def main():
    parser = argparse.ArgumentParser(
        description="Simple media organizer for Jellyfin")
    parser.add_argument("-s", "--season", type=int,
                        help="Force season number", default="1")
    parser.add_argument("-t", "--target", type=Path, default=Path.cwd(),
                        help="Target directory (default: current)")
    parser.add_argument("-i", "--interactive", action="store_true",
                        help="Interactive mode")

    locale_group = parser.add_argument_group("Subtitle Locale Fixing Options")
    locale_group.add_argument("--fix-sub", action="store_true",
                              help="Enable subtitle filename locale fixing")
    locale_group.add_argument("--locale-csv", type=Path,
                              help="CSV file with mapping rules (source,target,is_case_sensitive)")
    locale_group.add_argument("--locale-rule", action="append", nargs=3,
                              metavar=("source", "target", "case_sensitive"),
                              help="CLI rule: source target true/false (overrides CSV)")
    locale_group.add_argument("--default-locale", type=str, default=None,
                              help="Default locale to append if missing")

    args = parser.parse_args()

    fixer = SubtitleLocaleFixer()
    if args.fix_sub:
        mappings: list[SubtitleLocaleFixer.Rule] = []

        if args.locale_rule:
            mappings.extend(
                SubtitleLocaleFixer.Rule(
                    source=src, target=tgt, case_sensitive=cs.lower() == "true")
                for src, tgt, cs in args.locale_rule)

        if args.locale_csv and args.locale_csv.is_file():
            mappings.extend(SubtitleLocaleFixer.Rule.from_csv(args.locale_csv))

        fixer.default_locale = args.default_locale
        fixer.rules = mappings

    organizer = MediaOrganizer(target=args.target, sub_fixer=fixer)

    if args.interactive:
        organizer.process_interactive()
    else:
        organizer.organize_directory(args.season)


if __name__ == "__main__":
    main()
