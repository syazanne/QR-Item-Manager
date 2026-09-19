# License review

Reviewed on 19 September 2026 for **Project 1**. This covers the five direct
dependencies installed in the development environment and identifies the
scanner's embedded JavaScript decoder. It is not a complete audit of every
transitive dependency, future package version, or Project 2.

## This project's license

There is currently no project `LICENSE` file in this branch. Public visibility
alone does not grant general reuse or modification rights; see
[GitHub's licensing guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository).

The [MIT License](https://choosealicense.com/licenses/mit/) is an option matching
the intended broad reuse: it allows personal and commercial use, modification,
and distribution while requiring preservation of its copyright and license
notice. It includes a warranty disclaimer. This is a recommendation, not a
license grant; the owner still needs to select and apply a license to code they
have the right to license. Dependencies retain their own licenses.

## Direct dependencies

License texts were checked against the installed distributions where available
and the upstream sources linked below.

| Package checked | License | Source |
| --- | --- | --- |
| Streamlit 1.50.0 | Apache-2.0 | [Official terms](https://streamlit.io/terms-of-use) |
| qrcode 8.2 | BSD-3-Clause, with a retained upstream MIT notice | [License](https://github.com/lincolnloop/python-qrcode/blob/main/LICENSE) |
| Pillow 11.3.0 | MIT-CMU; bundled components have additional notices | [License information](https://pillow.readthedocs.io/en/stable/about.html#license) |
| pypdf 6.18.1 | BSD-3-Clause | [License](https://github.com/py-pdf/pypdf/blob/main/LICENSE) |
| streamlit-qrcode-scanner 0.1.2 | MIT (from its installed `.dist-info/LICENSE`) | [Upstream project](https://github.com/phamxtien/streamlit_qrcode_scanner) |

The top-level licenses above allow commercial as well as noncommercial use,
subject to their terms. They do not describe all embedded code: the scanner
review below found additional license notices. A library or hospital using Streamlit to run this app
does not, merely because of that use, owe a Streamlit software license fee.
Paid hosting or support is a separate service. Permission to use these
dependencies does not replace the missing license for this project's own code.

## Scanner and redistribution

`scanner.py` copies `html5-qrcode.min.js` from the installed scanner package to
the generated local component. A byte-for-byte comparison matched the installed
file to **html5-qrcode 2.3.4**, from its
[npm release archive](https://registry.npmjs.org/html5-qrcode/-/html5-qrcode-2.3.4.tgz).

- Size: 374,153 bytes.
- SHA-256: `ee7d5143d0dd97b82d9ceefd36befcf00e1b6ce6ba2c15a1713ac8fa44168e41`.
- The release's top-level `LICENSE` is Apache-2.0.
- Its `third_party/zxing-js.umd.js` contains Apache-2.0 notices and Oracle
  notices specifying **GPL version 2 only with the Classpath exception** for
  `OutputStream` and `ByteArrayOutputStream`. Their method implementations are
  also present in the installed minified decoder.

The corresponding source is available in the
[upstream v2.3.4 file](https://raw.githubusercontent.com/mebjas/html5-qrcode/v2.3.4/third_party/zxing-js.umd.js).
An [upstream discussion](https://github.com/zxing-js/library/issues/490) raises
the same licensing question; that discussion is not a legal determination.

**Finding:** do not describe the complete decoder as MIT-only or Apache-only.
Adding an MIT license for our own code and a notices file does not, on its own,
resolve the obligations of the embedded GPL-covered portions. The Classpath
exception matters, so this finding also does not establish that the whole app
must be GPL-licensed. It is not evidence of a required paid decoder subscription.

Before public distribution, either establish and fulfil the exact license,
source-availability, and notice obligations for this bundle, or replace it with
a decoder whose complete distribution can be checked more simply. A candidate
for evaluation is [jsQR](https://github.com/cozmo/jsQR): its current published
source declares [Apache-2.0](https://github.com/cozmo/jsQR/blob/master/LICENSE),
but its chosen release still needs inspection and camera/decoding tests before
adoption. No decoder replacement or new project license has been applied.

When sharing packaged dependencies or serving copied JavaScript, include the
applicable license texts, copyright notices, and any required NOTICE files.
Keep the notices for embedded components as well. Apache 2.0 also requires
notices of modifications to redistributed modified files; see its
[redistribution terms](https://www.apache.org/licenses/LICENSE-2.0#redistribution).
Source links in this review are not substitutes for the required license copies.
The decoder has now been identified; resolving the mixed-license finding above
remains open. Do not treat this review as sign-off for a packaged release.

`requirements.txt` specifies minimum versions, so a new installation may resolve
different versions. Recheck their license files when preparing a release.

## Retained PDF helper

`pdf_utils.py` is reference-only and is not imported by the current app. It has
an optional PyMuPDF fallback, which is not in `requirements.txt`. PyMuPDF has
[AGPL or commercial licensing](https://pymupdf.readthedocs.io/en/latest/about.html);
review those obligations if that fallback is enabled or redistributed. The
current QR-label feature uses pypdf.

## Scope of this review

Software license permission does not certify the app for a particular
institution's operations. The current app has no login or access controls.
An institution should assess its own deployment and data requirements. This
review is general information, not a guarantee of legal compliance or legal
advice for a particular deployment.
