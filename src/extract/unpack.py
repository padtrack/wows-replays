"""
This script should be placed in the root of a WoWS installation.
It will generate and populate res_extract.

Make sure you have the unpacker:
https://forum.worldofwarships.eu/topic/113847-all-wows-unpack-tool-unpack-game-client-resources/
"""

import argparse
import os
import shutil
import subprocess

OUTPUT_NAME = "res_extract"
INCLUDE_LIST = (
    "content/GameParams.data",
    "gui/achievements/*",
    "gui/battle_hud/damage_widget/*",
    "gui/battle_hud/indicators/modules/*",
    "gui/battle_hud/lower_log_modifiers/*",
    "gui/battle_hud/own_ship_health/*",
    "gui/battle_hud/state_panel/*",
    "gui/clans/*",
    "gui/consumables/consumable_*",
    "gui/data/constants/*",
    "gui/fla/minimap/*",
    "gui/fonts/*.ttf",
    "gui/powerups/*",
    "gui/pve/operation_icons/*",
    "gui/ribbons/*.png",
    "gui/service_kit/battle_types/*",
    "gui/service_kit/building_icons/*",
    "gui/service_kit/ship_classes/*",
    "gui/ship_bars/*",
    "scripts/*",
    "spaces/*/minimap*.png",
    "spaces/*/space.settings",
)
EXCLUDE_LIST = (
    "gui/consumables/consumable_*_empty.png",
    "gui/service_kit/battle_types/*big*",
    "gui/service_kit/battle_types/*small*",
    "gui/service_kit/battle_types/*tiny*",
    "gui/service_kit/battle_types/*disabled*",
)


def main(bin_num):
    bin_path = rf"bin\{bin_num}"
    idx_path = rf"{bin_path}\idx"
    pkg_path = r"..\..\..\res_packages"
    include = [i for pattern in INCLUDE_LIST for i in ("-I", pattern)]
    exclude = [i for pattern in EXCLUDE_LIST for i in ("-X", pattern)]

    subprocess.run(
        ["wowsunpack.exe", "-x", idx_path, "-p", pkg_path, "-o", OUTPUT_NAME, *include, *exclude]
    )

    texts_src = rf"{bin_path}\res\texts"
    texts_dest = rf"{OUTPUT_NAME}\texts"
    shutil.copytree(texts_src, texts_dest)

    print("Extraction complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extracts game resources.")
    parser.add_argument("--bin", default=max(os.listdir("bin/")), help="The game version to use.")
    args = parser.parse_args()

    main(args.bin)
