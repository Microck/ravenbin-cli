<h1 align="center">ravenbin-cli</h1>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-mit-000000?style=flat-square" alt="license badge"></a>
</p>

---

`ravenbin` uploads files to [Raven Bin](https://ravenbin.com/) and downloads them from complete share URLs. It runs Raven's web client in headless Chromium, so the browser handles encryption and decryption.

## install

```bash
python3 -m pip install git+https://github.com/Microck/ravenbin-cli.git
python3 -m playwright install chromium
```

Python 3.9 or newer is required. To use a system browser, set `RAVENBIN_CHROMIUM_PATH` to its executable path.

## upload

```bash
ravenbin upload ./report.zip
ravenbin upload ./short-lived.log --expiry 5m
```

The complete share URL is printed to stdout. Errors go to stderr. The default expiry is `12h`; Raven also offers `5m`, `15m`, `1h`, `2h`, and `4h`.

## download

Pass the complete URL, including the decryption key after `#`:

```bash
link="$(ravenbin upload ./report.zip)"
ravenbin fetch "$link" --output ./copy.zip
ravenbin download "$link" --output ./copy.zip --force
```

`fetch` and `download` are the same command. If `--output` is omitted, the saved file uses Raven's filename. The command refuses to overwrite an existing path unless you pass `--force`. It prints the saved path to stdout.

Use `ravenbin --help`, `ravenbin upload --help`, or `ravenbin fetch --help` for the full command syntax. Both operations accept `--timeout` in seconds (default: 300).

## how it works

The browser runs Raven's current client. Uploads use its `Create Bin` flow, and downloads use its normal decryption and download flow. For uploads, the CLI stages a temporary copy under the user's home directory because some Chromium sandbox variants cannot read `/tmp`. It removes the copy after upload.

Raven currently limits users to six active bins and two uploads in progress. Its public service may be busy or unavailable. Share URLs are sensitive because the decryption key is stored after `#`; do not put them in logs or share them with people who should not read the file. Do not use Raven Bin as the only protection for credentials, private keys, or regulated data.

## license

MIT. Raven Bin is a separate service operated by Raven Technologies Group.
