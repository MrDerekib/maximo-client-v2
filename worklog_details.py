"""Compare rich-editor plain text without mistaking layout whitespace for data loss."""
import re
import unicodedata


def comparable_details(value):
    text=unicodedata.normalize('NFC',str(value or '')).replace('\r\n','\n').replace('\r','\n')
    # Browsers may serialize Excel tabs as spaces or NBSP. Preserve words,
    # punctuation, case, line order and internal blank lines.
    return '\n'.join(re.sub(r'[^\S\n]+',' ',line).strip() for line in text.split('\n')).strip()


def details_match(expected, actual):
    return comparable_details(expected)==comparable_details(actual)
