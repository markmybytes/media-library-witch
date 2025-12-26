import argparse
import csv
import os
import re
import shutil
from pathlib import Path
from typing import NamedTuple, Optional, Self


class SubtitleLocaleFixer:

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

    def organize_directory(self, season: Optional[str], directory: Path = None):
        if not directory:
            directory = self.target

        # if season is None:
        #     season_match = re.search(
        #         r"(?:s|season)\s*(\d+)", directory.name, re.I)
        #     season = int(season_match.group(1)) if season_match else 1

        video_files = []
        sub_files = []
        extra_candidates = []

        for item in directory.iterdir():
            if item.is_file():
                if item.suffix.lower() in {".mkv", ".mp4", ".m2ts", ".ts"}:
                    video_files.append(item)
                elif item.suffix.lower() in {".srt", ".ass", ".ssa", ".sup"}:
                    sub_files.append(item)
            elif item.is_dir():
                extra_candidates.append(item)

        # TODO
        if len(video_files) <= 2 and len(extra_candidates) >= 3:
            for subdir in extra_candidates:
                self.organize_directory(subdir, None)
            return

        season_dir = directory.joinpath(f"Season {season:02d}")
        extra_dir = directory.joinpath("EXTRA", f"Season {season:02d}")

        season_dir.mkdir(exist_ok=True)
        extra_dir.parent.mkdir(exist_ok=True)

        self._move_videos(video_files, season_dir)
        self._move_subtitles(sub_files, season_dir)
        self._move_extras(extra_candidates, extra_dir, season_dir)

    def _move_videos(self, files: list[Path], dest: Path):
        for f in files:
            f.rename(dest.joinpath(f.name))

    def _move_subtitles(self, files: list[Path], dest: Path):
        for f in files:
            fixed_name = self.sub_fixer.fix_name(f.name)
            dest.joinpath(fixed_name).write_bytes(f.read_bytes())
            f.unlink()

    def _move_extras(self, dirs: list[Path], extra_dest: Path, season_dest: Path):
        for d in dirs:
            name = d.name.lower()
            if any(x in name for x in ["bonus", "extra", "feature", "behind"]):
                shutil.move(str(d), str(extra_dest.joinpath(d.name)))


def main():
    parser = argparse.ArgumentParser(
        description="Simple media organizer for Jellyfin")
    parser.add_argument("-s", "--season", type=int, help="Force season number")
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

    organizer = MediaOrganizer(
        target=args.target,
        season=args.season,
        sub_fixer=fixer,
    )

    if args.interactive:
        organizer.process_interactive()
    else:
        organizer.organize_directory(args.season)


if __name__ == "__main__":
    main()
