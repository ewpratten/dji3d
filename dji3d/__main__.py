import argparse
import sys
import ffmpeg
import tempfile
import pysrt
import matplotlib.pyplot as plt
import json
import csv
from dataclasses import dataclass
import dataclasses
import os
from typing import List, Generator
import re

TELEMETRY_PARSE_RE = r"GPS \(([\d.-]+), ([\d.-]+), [\d.-]+\), D ([\d.-]+)m, H ([\d.-]+)m, H.S ([\d.-]+)m\/s, V.S ([\d.-]+)"


class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)


@dataclass
class PositionMeta:
    timestamp: str
    latitude: float
    longitude: float
    rel_elevation: float
    distance: float
    horizontal_velocity: float
    vertical_velocity: float

    def __repr__(self):
        return json.dumps(self.__dict__)


def parseSubs(subtitles: List[pysrt.srtitem.SubRipItem]) -> Generator[PositionMeta, None, None]:
    for message in subtitles:

        # Get message timestamp
        timestamp = message.start

        # Get raw telemetry text
        raw_telemetry = message.text

        # Parse telemetry
        telemetry_parsed = re.findall(TELEMETRY_PARSE_RE, raw_telemetry)[0]

        yield PositionMeta(
            timestamp=str(timestamp).split(",")[0],
            latitude=float(telemetry_parsed[1]),
            longitude=float(telemetry_parsed[0]),
            distance=float(telemetry_parsed[2]),
            rel_elevation=float(telemetry_parsed[3]),
            horizontal_velocity=float(telemetry_parsed[4]),
            vertical_velocity=float(telemetry_parsed[5])
        )


def main() -> int:

    # Handle CLI args
    ap = argparse.ArgumentParser(
        prog="dji3d",
        description="DJI3D is a tool for graphing 3d positional data extracted from DJI drone telemetry",
    )
    ap.add_argument("input", help="Raw drone video file with telemetry data")
    ap.add_argument("-i", "--interactive", help="Run interactively",
                    action="store_true", required=False)
    ap.add_argument("-f", "--format", help="Output format",
                    choices=["graph", "csv", "json"], default="graph", required=False)
    ap.add_argument("-o", "--output", help="Output location", required=False)
    args = ap.parse_args()

    # Handle text-only formats not being interactive
    if args.format in ["csv", "json"] and args.interactive:
        print("Interactive mode can not be used with text-based output formats")
        return 1

    # Handle non-interactive with no output
    if not args.interactive and not args.output:
        print(
            "If not running in interactive mode, an output file must be specified with -o")
        return 1

    # Check that the input file exists
    if not os.path.isfile(args.input):
        print(f"{args.input} is not a file")
        return 1

    # Get a temp file to write SRT output to
    temp_srt_file = tempfile.NamedTemporaryFile(suffix=".srt")

    # This file may already exist
    if os.path.exists(temp_srt_file.name):
        os.remove(temp_srt_file.name)

    # Use FFMPEG to parse the input file into SRT
    print(" :: Extracting subtitles from video")
    ffmpeg.input(args.input).output(temp_srt_file.name).run()

    # Load the SRT file
    print(" :: Parsing extracted subtitles")
    subtitles = pysrt.open(temp_srt_file.name)
    temp_srt_file.close()

    # Build a position list
    print(" :: Translating subtitles to GPS data")
    positions = list(parseSubs(subtitles))

    # Handle no data
    if len(positions) == 0:
        print("This file contained no parsable telemetry data")
        return 1

    # Handle possible program modes
    if args.format == "graph":
        print(" :: Plotting")

        # Set up plot axes
        ax = plt.axes(projection='3d')

        # Build plot data
        z = []
        x = []
        y = []
        for position in positions:
            z.append(position.rel_elevation)
            x.append(position.longitude)
            y.append(position.latitude)

        # Plot
        ax.plot3D(x, y, z)

        # Handle showing vs saving
        if args.interactive:
            print(" :: Showing MatPlotLib UI")
            plt.show()
        else:
            print(" :: Saving plot")
            plt.savefig(args.output)
    elif args.format == "json":
        print(" :: Writing JSON")
        json.dump(positions, open(args.output, "w"), cls=EnhancedJSONEncoder)
    elif args.format == "csv":
        print(" :: Writing CSV")
        with open(args.output, "w") as fp:
            writer = csv.writer(fp)
            writer.writerow([var for var in vars(positions[0])])
            for position in positions:
                writer.writerow([vars(position)[var]
                                 for var in vars(position)])

    return 0


if __name__ == "__main__":
    sys.exit(main())
