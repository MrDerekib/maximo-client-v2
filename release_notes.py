"""Per-user release-note history and offline fallback; no network or UI calls."""
from dataclasses import dataclass, replace
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
    from_version: str = ''


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
    text = ''
    try:
        text = Path(changelog or PROGRAM_DIR / 'CHANGELOG.md').read_text(encoding='utf-8')
        local = changelog_section(text, current_version)
    except (OSError, UnicodeError):
        local = ''
    state = _read_state(path)
    cached = state['cached_release']
    def result(markdown, source):
        notes = ReleaseNotes(format_version_tag(current_version), markdown[:MAX_NOTES_CHARS], url, source)
        return accumulated_release_notes(notes, text, state['seen_version'])
    if same_version(cached.get('tag'), current_version) and isinstance(cached.get('markdown'), str):
        markdown = cached['markdown'].strip()
        if markdown:
            if isinstance(cached.get('url'), str) and cached['url']:
                url = cached['url']
            summary = summary_section(markdown)
            if summary:
                return result(summary, 'github')
            # An older/full GitHub body must not hide the summary bundled in this version.
            summary = summary_section(local)
            if summary:
                return result(summary, 'changelog')
            return result(markdown, 'github')
    return result(summary_section(local) or local, 'changelog')


def accumulated_release_notes(notes, changelog, previous_version):
    """Include only releases newer than the known base, through the installed build.

    The bundled history supplies skipped releases without additional requests.
    Missing/invalid history falls back to the installed release alone.
    """
    if (not re.fullmatch(r'v?\d+\.\d+(?:\.\d+){0,2}', previous_version or '')
            or not is_newer(notes.version, previous_version)):
        return notes
    notes = replace(notes, from_version=format_version_tag(previous_version))
    headings = re.finditer(r'^##[ \t]+\[?(v?\d+\.\d+(?:\.\d+){0,2})\]?(?=[ \t\r\n—–:-]|$).*$', changelog, re.MULTILINE)
    releases = []
    for heading in headings:
        version = heading.group(1)
        if (is_newer(version, previous_version) and is_newer(notes.version, version)
                and not any(same_version(version, other[0]) for other in releases)):
            section = changelog_section(changelog, version)
            summary = summary_section(section) or section.partition('\n')[2].strip()
            if summary: releases.append((version, summary))
    if not releases:
        return notes
    if notes.markdown: releases.append((notes.version, notes.markdown))
    releases.sort(key=lambda item: tuple(int(n) for n in item[0].lstrip('v').split('.')), reverse=True)
    markdown = '\n\n'.join(f'## {format_version_tag(version)}\n\n{summary}' for version, summary in releases)
    return replace(notes, markdown=markdown[:MAX_NOTES_CHARS], source='combined')
