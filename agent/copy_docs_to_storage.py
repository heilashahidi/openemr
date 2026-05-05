"""One-shot: copy sample_docs into OpenEMR's document storage and wire up rows.

OpenEMR convention (from library/classes/Document.class.php):
- Path: <repo>/<pid>/<uuid>
- path_depth = 1
- url = file://<absolute-path>/<uuid>
- drive_uuid = binary(16), encrypted flag per-document

drive_encryption is globally on in this dev install, so we set encrypted=0 on
each row to make OpenEMR skip the decrypt step on read.
"""
import hashlib
import os
import subprocess
import uuid

SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "sample_docs")
OEMR_REPO = "/var/www/localhost/htdocs/openemr/sites/default/documents"


def docker_id(filter_str):
    out = subprocess.run(
        f"docker ps --format '{{{{.ID}}}} {{{{.Image}}}}' | grep {filter_str}",
        shell=True, capture_output=True, text=True,
    ).stdout.strip().split("\n")[0].split()
    return out[0] if out else None


def sql(db_cid, query):
    r = subprocess.run(
        ["docker", "exec", "-i", db_cid, "mariadb", "-u", "root", "-proot", "openemr"],
        input=query, capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr)
    return r.stdout


def main():
    db_cid = docker_id("mariadb")
    oemr_cid = docker_id("openemr/openemr")
    if not db_cid or not oemr_cid:
        raise SystemExit(f"Container not found: db={db_cid} oemr={oemr_cid}")

    rows = sql(db_cid, "SELECT id, foreign_id, name FROM documents WHERE foreign_id IN (10,11,12,13) ORDER BY id;").strip().split("\n")[1:]

    for line in rows:
        doc_id, pid, name = line.split("\t")
        doc_id, pid = int(doc_id), int(pid)

        # Source file
        subdir = "intake-forms" if "intake" in name else "lab-results"
        src = os.path.join(SAMPLE_DIR, subdir, name)
        if not os.path.exists(src):
            print(f"  SKIP {name}: source not found at {src}")
            continue

        # Compute target
        file_uuid = str(uuid.uuid4())
        dst_dir = f"{OEMR_REPO}/{pid}"
        dst_path = f"{dst_dir}/{file_uuid}"

        with open(src, "rb") as f:
            data = f.read()
        size = len(data)
        sha1 = hashlib.sha1(data).hexdigest()

        # Ensure dir exists in container, copy file, fix perms
        subprocess.run(["docker", "exec", oemr_cid, "mkdir", "-p", dst_dir], check=True)
        subprocess.run(["docker", "cp", src, f"{oemr_cid}:{dst_path}"], check=True)
        subprocess.run(["docker", "exec", oemr_cid, "chown", "-R", "apache:apache", dst_dir], check=True)
        subprocess.run(["docker", "exec", oemr_cid, "chmod", "0700", dst_dir], check=True)
        subprocess.run(["docker", "exec", oemr_cid, "chmod", "0600", dst_path], check=True)

        # Update DB row
        url = f"file://{dst_path}"
        sql(db_cid,
            f"UPDATE documents SET "
            f"url='{url}', "
            f"path_depth=1, "
            f"drive_uuid=UNHEX(REPLACE('{file_uuid}','-','')), "
            f"encrypted=0, "
            f"hash='{sha1}', "
            f"size={size} "
            f"WHERE id={doc_id};"
        )
        print(f"  ✅ doc {doc_id} (pid={pid}) {name} → {dst_path} ({size} bytes)")

    print("\nDone.")


if __name__ == "__main__":
    main()
