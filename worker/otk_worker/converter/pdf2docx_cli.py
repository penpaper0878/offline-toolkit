"""Run pdf2docx in its own process, so a cancel can stop it: python -m otk_worker.converter.pdf2docx_cli in.pdf out.docx"""

import logging
import sys


def main() -> None:
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    from pdf2docx import Converter

    src, out = sys.argv[1], sys.argv[2]
    cv = Converter(src)
    try:
        cv.convert(out, multi_processing=False)
    finally:
        cv.close()


if __name__ == "__main__":
    main()
