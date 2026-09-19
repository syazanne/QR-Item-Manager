# License review

Reviewed on 19 September 2026 for **project-1-item-manager2**. This branch uses
jsQR on port 8502. The `project-1-item-manager` branch retains the original
decoder and license-review findings; its local 8501 checkout has been backed
up and removed. The original branch is now stored in `syazanne/private-project`,
a separate private GitHub repository; its branch in `QR-Item-Manager` was deleted.

## This project's license

The original application code and documentation in this checkout are licensed
under the [MIT License](../LICENSE), copyright 2026 syazanne. The copyright name
matches this project's Git author. Keep that license and copyright notice when
redistributing the original code or substantial portions of it.

MIT permits personal and commercial use, modification and redistribution. It
does not require a usage fee and provides no warranty. Dependencies and their
notices retain their own licenses; the root MIT file does not relicense them.
See [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). This change does not apply
a license to the separate Project 2 branch or replace the original branch's
decoder. Other branches and historical checkouts must be assessed separately.

## Decoder adopted: jsQR 1.4.0

The exact [npm release](https://registry.npmjs.org/jsqr/-/jsqr-1.4.0.tgz) was inspected,
along with its metadata, production TypeScript source and webpack configuration
at commit [`49a9633931fb8030ac2fc9cecc121d6e5a19f9a3`](https://github.com/cozmo/jsQR/tree/49a9633931fb8030ac2fc9cecc121d6e5a19f9a3).

- The archive's SHA-512 matches the npm registry integrity value:
  `sha512-dxLob7q65Xg2DvstYkRpkYtmKm2sPJ9oFhrhmudT1dZvNFFTlroai3AWSpLey/w5vMcLBXRgOJsbXpdN9HzU/A==`.
- `package.json` and the full `LICENSE` declare **Apache-2.0**.
- The release declares no runtime dependencies. Production source imports are
  internal to jsQR; development/test packages are not needed by the app.
- The reviewed release and source tree have no separate `NOTICE` file. No GPL,
  Classpath-exception or Oracle notices were found in the reviewed production
  sources or distributed JavaScript. This is a scoped source review, not proof
  about every possible copyright claim.
- `scanner_frontend/vendor/jsQR.js` is copied without modification from
  `package/dist/jsQR.js`. SHA-256:
  `bc40c8a15196236b2314db0856f72ca0b49980cd5413b8c852a7349f5fee0859`.
- The full upstream license is retained in
  [LICENSE.jsQR.txt](../scanner_frontend/vendor/LICENSE.jsQR.txt), with provenance
  and contributor attribution in [NOTICES.txt](../scanner_frontend/vendor/NOTICES.txt).
  Both files are copied alongside the decoder into the served component.

Apache 2.0 permits royalty-free use and redistribution subject to its terms.
Keep the supplied license and attribution with the decoder. If the decoder is
modified later, identify the modifications as required by the license. See
[Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0) and the project's
[third-party notices](../THIRD_PARTY_NOTICES.md).

The camera is controlled through browser media APIs. Frames are decoded locally
in the browser; only decoded text is sent to the Streamlit app. The scanner loads
no decoder from a CDN and does not import `streamlit-qrcode-scanner`.
Its generated assets use `data/scanner_component_jsqr/`, so old generated
html5-qrcode files are not part of the served component.

## Why the old decoder was replaced

The original `streamlit-qrcode-scanner 0.1.2` package contains an exact copy of
html5-qrcode 2.3.4 (SHA-256
`ee7d5143d0dd97b82d9ceefd36befcf00e1b6ce6ba2c15a1713ac8fa44168e41`).
That release declares Apache-2.0 at the top level, but its
[embedded ZXing source](https://raw.githubusercontent.com/mebjas/html5-qrcode/v2.3.4/third_party/zxing-js.umd.js)
contains GPLv2-with-Classpath-exception notices on `OutputStream` and
`ByteArrayOutputStream`; their implementations are present in the minified bundle.

This migration removes the old Python scanner dependency and uses jsQR instead.
It does not relicense the old decoder or claim to resolve its redistribution
obligations. The original checkpoint remains available on its original branch.
The old package and generated scanner assets have also been removed from this
development environment. The original app can be installed independently from
its own branch and requirements; this jsQR version does not need that package.

## Python dependencies

| Package checked | Top-level license | Source |
| --- | --- | --- |
| Streamlit 1.50.0 | Apache-2.0, with frontend/font notices | [Release license](licenses/streamlit-1.50.0/LICENSE) and [NOTICES](licenses/streamlit-1.50.0/NOTICES) |
| qrcode 8.2 | BSD-3-Clause, with a retained upstream MIT notice | [Retained license](licenses/qrcode-8.2/qrcode-8.2.dist-info/LICENSE) |
| Pillow 11.3.0 | MIT-CMU; bundled components have additional notices | [Retained license and notices](licenses/pillow-11.3.0/pillow-11.3.0.dist-info/licenses/LICENSE) |
| pypdf 6.18.1 | BSD-3-Clause | [Retained license](licenses/pypdf-6.18.1/pypdf-6.18.1.dist-info/licenses/LICENSE) |

These packages' top-level licenses permit commercial and noncommercial use,
subject to their terms. Running Streamlit locally does not require a paid
Streamlit software subscription. Hosting and support services are separate.
The [dependency inventory](licenses/README.md) records all **38 packages** in
the installed default Python runtime dependency graph, including transitive
dependencies, for Python 3.9.6 on this macOS development environment. It retains
**54 full license/notice files** and their hashes. Streamlit's files were fetched
from its official `1.50.0` tag; the remaining files came from the installed
distributions. No Python dependency binaries or source trees are vendored here.

The review covers distribution metadata and retained license/notice files,
plus the decoder source review above. It is not a line-by-line provenance audit
of every Python package or Streamlit's entire frontend. Relevant findings:

- **certifi uses MPL-2.0.** This is file-level copyleft, not a requirement to
  license this application's independent files under MPL. Its license is
  retained. Its exact distribution and source-download page are recorded in
  the inventory. If redistributing certifi binaries, provide the required
  source availability notice; modifications to covered files remain subject
  to MPL. See [Mozilla's official FAQ](https://www.mozilla.org/en-US/MPL/2.0/FAQ/).
- **NumPy's wheel includes native-library notices**, including GPL with the
  GCC Runtime Library Exception. The full license and exception are retained;
  this is not the old QR decoder issue. Do not describe the entire environment
  as MIT-only or GPL-free. Binary redistribution needs the actual wheel's
  native-library terms and any applicable source obligations checked.
- **Pillow and PyArrow include additional component licenses and notices.**
  These are retained in full, including the JPEG and FreeType attributions.
- **Streamlit's NOTICES includes frontend dependencies and font licenses.**
  Some entries offer alternative licenses: DOMPurify offers Apache-2.0 or MPL,
  and JSZip offers MIT or GPL; the permissive alternative is available for
  each. The supplied notices are preserved without removing the alternatives.

`requirements.txt` specifies minimum versions. A new installation, OS or Python
version may resolve different packages. This inventory is a dated snapshot,
not a lockfile, and must be refreshed when the dependency set changes.

## Retained PDF helper

`pdf_utils.py` remains reference-only and is not imported by the current app.
Its unused optional PyMuPDF/fitz fallback has been removed from this branch;
both the helper and QR-label PDFs use pypdf. No PyMuPDF installation is needed.

## Sharing this version

`QR-Item-Manager` is public. The original port-8501 branch has been copied to
the private `private-project` repository and deleted from this public repository.
GitHub visibility is set for a repository, not separately for its branches; see
[GitHub's visibility documentation](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility).
This review applies to the current jsQR source files, not the whole repository
history or other branches. Deleting a branch does not erase commits shared with
other branches or make previously public copies private. No historical rewrite
has been performed. When sharing this reviewed source as a ZIP, select this
branch; do not include `.git`, local environments or recovery archives.

For the current **GitHub source checkout / source ZIP**, keep:

1. The root `LICENSE` and `THIRD_PARTY_NOTICES.md`.
2. The complete `scanner_frontend/vendor/` folder, including its license and
   attribution; the component also serves those files alongside the decoder.
3. This review and `docs/licenses/`, which preserve the inspected notices.

Users install Python dependencies separately with pip. The repository ignores
`.venv`, local databases, generated scanner bundles, QR images and backups;
share the branch's source files rather than zipping the working directory.
The old decoder is absent from the new requirements and vendored scanner.

An executable, Docker image, bundled virtual environment or hosted browser
build is a different distribution artifact. Before publishing one, inspect its
actual contents and versions, preserve required notices and meet any applicable
source-availability obligations. The current review does not certify an
unbuilt binary package. No such package is produced by this project today.

## Scope

This review documents the inspected release and the changes made; it is not
legal advice or a guarantee of legal compliance. Software license permission
does not certify an institution's deployment. The app has no login/access
controls; organisations should assess their own operational and data needs.
