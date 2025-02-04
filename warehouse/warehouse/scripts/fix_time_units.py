import os
from sys import exit
import argparse
from tqdm import tqdm
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from warehouse.util import con_message


def fix_units(inpath, outpath, time_units, offset):
    import xarray as xr

    with xr.open_dataset(inpath, decode_times=False) as ds:
        if ds.get("time") is None:
            con_message("error", f"{os.path.basename(inpath)} has no 'time' axis")
            exit(1)
        bnds_name = "time_bnds" if ds.get("time_bnds") is not None else "time_bounds"
        if ds["time"].attrs.get("units") != time_units:
            ds = ds.assign_coords(time=ds["time"] + offset)
            if bnds_name == "time_bnds":
                ds = ds.assign_coords(time_bnds=ds[bnds_name] + offset)
            else:
                ds = ds.assign_coords(time_bounds=ds[bnds_name] + offset)
            if ds[bnds_name].values[0][0] == ds[bnds_name].values[0][1]:
                freq = ds[bnds_name].values[1][1] - ds[bnds_name].values[1][0]
                ds[bnds_name].values[0][0] -= freq
            ds["time"].attrs = {
                "long_name": "time",
                "units": time_units,
                "calendar": "noleap",
                "bounds": bnds_name,
            }
            ds["time_bnds"].attrs = {"long_name": "time interval endpoints"}
            ds.to_netcdf(outpath, unlimited_dims=["time"])
        else:
            os.symlink(inpath, outpath)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "input", help="path to directory containing data with incorrect time units"
    )
    parser.add_argument(
        "output", help="path to directory where corrected data should be saved"
    )
    parser.add_argument(
        "-t",
        "--time-offset",
        type=float,
        default=0.0,
        help="Value to increase time and time_bnds index by",
    )
    parser.add_argument("-d", "--time-units", default="days since 1850-01-01 00:00:00")
    parser.add_argument(
        "-p", "--processes", default=6, type=int, help="Number of parallel processes"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Suppress progress bars"
    )
    args = parser.parse_args()
    os.makedirs(args.output, exist_ok=True)

    total = 0
    for _ in Path(args.input).glob("*"):
        total += 1
    with ProcessPoolExecutor(max_workers=args.processes) as pool:
        futures = []
        for path in Path(args.input).glob("*"):
            inpath = str(path.resolve())
            outpath = str(Path(args.output, path.name).resolve())
            if args.processes > 1:
                futures.append(
                    pool.submit(
                        fix_units, inpath, outpath, args.time_units, args.time_offset
                    )
                )
            else:
                fix_units(inpath, outpath, args.time_units, args.time_offset)
        if args.processes > 1:
            for _ in tqdm(as_completed(futures), total=total, disable=args.quiet):
                pass
    return 0


if __name__ == "__main__":
    exit(main())
