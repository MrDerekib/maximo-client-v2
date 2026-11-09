"""Per-user release-note history and offline fallback; no network or UI calls."""
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import re

from app_paths import PROGRAM_DIR, create_unique_file
from update_checker import format_version_tag, is_newer

MAX_NOTES_CHARS = 100_000
STATE_FILENAME = 'release_notes_state.json'


@dataclass(frozen=True)
class ReleaseNotes:
    version: str
    markdown: str
    url: str = ''
    source: str = ''


def same_version(first, second):
    return bool(isinstance(first, str) and isinstance(second, str) and first and second
                and not is_newer(first, second) and not is_newer(second, first))


def _read_state(path):
    path = Path(path)
    try:
        if path.stat().st_size > 512_000:
            raise ValueError('Archivo de estado demasiado grande')
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or data.get('schema_version') != 1:
            raise ValueError('Formato de estado no reconocido')
        seen = data.get('seen_version', '')
        cached = data.get('cached_release', {})
        return {'schema_version': 1, 'seen_version': seen if isinstance(seen, str) else '',
                'cached_release': cached if isinstance(cached, dict) else {}}
    except FileNotFoundError:
        pass
    except (OSError, ValueError):
        logging.warning('No se pudo leer el historial de novedades; se reconstruirá al guardar.')
    return {'schema_version': 1, 'seen_version': '', 'cached_release': {}}


def _write_state(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = create_unique_file(path.parent, 'release-notes-', '.tmp')
    try:
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def initialize_history(path, current_version):
    """A fresh configuration starts at its installed version, without an update popup."""
    if not Path(path).exists():
        _write_state(path, {'schema_version': 1, 'seen_version': format_version_tag(current_version),
                            'cached_release': {}})


def should_show_notes(path, current_version):
    seen = _read_state(path)['seen_version']
    return is_newer(current_version, seen or '0.0.0')


def mark_notes_seen(path, current_version):
    state = _read_state(path)
    if is_newer(current_version, state['seen_version'] or '0.0.0'):
        state['seen_version'] = format_version_tag(current_version)
        _write_state(path, state)


def cache_release_notes(path, tag, markdown, url=''):
    if not isinstance(markdown, str) or not markdown.strip():
        return
    state = _read_state(path)
    state['cached_release'] = {'tag': tag, 'markdown': markdown[:MAX_NOTES_CHARS], 'url': url}
    _write_state(path, state)


def changelog_section(text, current_version):
    """Only the installed version's H2 section, never the entire release history."""
    headings = list(re.finditer(r'^##[ \t]+\[?(v?\d+\.\d+(?:\.\d+){0,2})\]?(?=[ \t\r\n—–:-]|$).*$',
                                text, re.MULTILINE))
    for index, heading in enumerate(headings):
        if same_version(heading.group(1), current_version):
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            return text[heading.start():end].strip()[:MAX_NOTES_CHARS]
    return ''


def summary_section(markdown):
    """Read the explicit Resumen block, ending at the next H1/H2/H3 heading."""
    heading = re.search(r'^###[ \t]+Resumen[ \t]*\r?$', markdown, re.MULTILINE | re.IGNORECASE)
    if heading is None:
        return ''
    remaining = markdown[heading.end():]
    following = re.search(r'^#{1,3}[ \t]+', remaining, re.MULTILINE)
    return remaining[:following.start() if following else len(remaining)].strip()


def installed_release_notes(path, current_version, changelog=None, fallback_url=''):
    url = fallback_url or ('https://github.com/MrDerekib/maximo-client-v2/releases/tag/' +
                           format_version_tag(current_version))
    try:
        text = Path(changelog or PROGRAM_DIR / 'CHANGELOG.md').read_text(encoding='utf-8')
        local = changelog_section(text, current_version)
    except (OSError, UnicodeError):
        local = ''
    cached = _read_state(path)['cached_release']
    if same_version(cached.get('tag'), current_version) and isinstance(cached.get('markdown'), str):
        markdown = cached['markdown'].strip()
        if markdown:
            if isinstance(cached.get('url'), str) and cached['url']:
                url = cached['url']
            summary = summary_section(markdown)
            if summary:
                return ReleaseNotes(format_version_tag(current_version), summary[:MAX_NOTES_CHARS], url, 'github')
            # An older/full GitHub body must not hide the summary bundled in this version.
            summary = summary_section(local)
            if summary:
                return ReleaseNotes(format_version_tag(current_version), summary[:MAX_NOTES_CHARS], url, 'changelog')
            return ReleaseNotes(format_version_tag(current_version), markdown[:MAX_NOTES_CHARS], url, 'github')
    return ReleaseNotes(format_version_tag(current_version), summary_section(local) or local, url, 'changelog')
