"""Native Registro.Resumen maxlength verified in Maximo on 2026-11-16."""
WORKLOG_SUMMARY_MAX_LENGTH = 100


def summary_length(text):
    # HTML maxlength and Qt QString both count UTF-16 code units.
    return len(str(text).encode("utf-16-le", errors="surrogatepass")) // 2


def validate_worklog_summary(text, field="Resumen"):
    length = summary_length(text)
    if length > WORKLOG_SUMMARY_MAX_LENGTH:
        raise ValueError(f"{field} admite como máximo {WORKLOG_SUMMARY_MAX_LENGTH} caracteres "
                         f"({length} introducidos). Usa Detalles para el texto extenso.")
    return text
