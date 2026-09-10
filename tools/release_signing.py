"""Isolated signing and verification using the checked-in App archive key."""

import os
from pathlib import Path
import shutil

from release_common import ROOT, config, relative_path, run, work_path


def primary_fingerprints(output):
    result = []
    primary = False
    for line in output.decode().splitlines():
        row = line.split(":")
        if row[0] in ("pub", "sec"):
            primary = True
        elif row[0] in ("sub", "ssb"):
            primary = False
        elif row[0] == "fpr" and primary:
            result.append(row[9])
            primary = False
    return result


class Signing:
    def __init__(self, workspace, settings=None):
        self.settings = settings or config()
        self.workspace = work_path(Path(workspace))
        self.home = self.workspace / "gnupg"
        self.keyring = self.workspace / "trusted.gpg"
        self.fingerprint = self.settings["signing_fingerprint"]
        self.public_key = ROOT / relative_path(self.settings["signing_key"])
        self.passphrase = None

    def __enter__(self):
        self.workspace.mkdir(parents=True, exist_ok=False)
        self.home.mkdir(mode=0o700)
        initialized = False
        try:
            public = self.public_key.read_bytes()
            shown = run(self.gpg("--with-colons", "--show-keys"), input=public)
            if primary_fingerprints(shown.stdout) != [self.fingerprint]:
                raise ValueError("Archive public key does not match its checked-in fingerprint")
            self.keyring.write_bytes(run(self.gpg("--dearmor"), input=public).stdout)
            initialized = True
            return self
        finally:
            if not initialized:
                self.close()

    def gpg(self, *arguments):
        return ["gpg", "--no-options", "--batch", "--homedir", self.home, *arguments]

    def import_key(self, private_key, passphrase):
        if not private_key or b"\n" in passphrase or b"\r" in passphrase:
            raise ValueError("A private signing key and a single-line passphrase are required")
        run(self.gpg("--import"), input=private_key)
        listed = run(self.gpg("--with-colons", "--list-secret-keys"))
        if primary_fingerprints(listed.stdout) != [self.fingerprint]:
            raise ValueError("Imported signing key does not match the archive trust contract")
        self.passphrase = passphrase

    def import_environment(self):
        private = os.environ.pop("CLAW_APPS_APT_SIGNING_PRIVATE_KEY", "")
        if "CLAW_APPS_APT_SIGNING_PASSPHRASE" not in os.environ or not private:
            raise ValueError("Both dedicated App APT signing secrets must be configured")
        passphrase = os.environ.pop("CLAW_APPS_APT_SIGNING_PASSPHRASE")
        self.import_key(private.encode(), passphrase.encode())

    def sign(self, source, destination, *, clear=False, armored=False):
        if self.passphrase is None:
            raise ValueError("Unsigned App publication is forbidden")
        arguments = [
            "--yes", "--pinentry-mode", "loopback", "--passphrase-fd", "0",
            "--local-user", self.fingerprint, "--digest-algo", "SHA512",
            "--output", destination,
        ]
        if armored:
            arguments.append("--armor")
        arguments.extend(["--clearsign" if clear else "--detach-sign", source])
        run(self.gpg(*arguments), input=self.passphrase + b"\n")
        if clear:
            if self.verify_clear(destination) != source.read_bytes():
                raise ValueError("New InRelease signature does not reproduce Release")
        else:
            self.verify(destination, source)

    def verify(self, signature, source):
        run(["gpgv", "--homedir", self.home, "--keyring", self.keyring, signature, source])

    def verify_clear(self, source):
        return run(["gpgv", "--homedir", self.home, "--keyring", self.keyring,
                    "--output", "-", source]).stdout

    def close(self):
        if self.home.exists():
            run(["gpgconf", "--homedir", self.home, "--kill", "gpg-agent"], check=False)
        self.passphrase = None
        if self.workspace.exists():
            shutil.rmtree(self.workspace)

    def __exit__(self, *_):
        self.close()
