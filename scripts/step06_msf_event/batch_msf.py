import subprocess
from pathlib import Path
import re

EPISODE_DIR = Path("episode")
MSF_SCRIPT = "MSF.py"

pattern = re.compile(r"friends_s\d{2}_e\d{2}\.docx$", re.IGNORECASE)


def main():

    if not EPISODE_DIR.exists():
        print("episode directory not found.")
        return

    docx_files = sorted(
        f for f in EPISODE_DIR.iterdir()
        if f.is_file() and pattern.match(f.name)
    )

    if not docx_files:
        print("No episode docx files found.")
        return

    print(f"Found {len(docx_files)} episodes.\n")

    for docx in docx_files:

        episode_id = docx.stem
        out_dir = Path("msf_output") / episode_id

        cmd = [
            "python",
            MSF_SCRIPT,
            "--docx",
            str(docx),
            "--out_dir",
            str(out_dir)
        ]

        print("=" * 60)
        print("Processing:", docx.name)
        print("Output dir:", out_dir)
        print("=" * 60)

        subprocess.run(cmd, check=True)

    print("\nAll episodes processed.")


if __name__ == "__main__":
    main()