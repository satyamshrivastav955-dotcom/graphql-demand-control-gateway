"""
GraphQL Argument Injection Detector.
Scans field argument values and variables for SQLi, NoSQLi, XSS, and command injection patterns.
"""
import re
from typing import Dict, Any
from graphql.language.visitor import Visitor, visit
from graphql.language.ast import DocumentNode, StringValueNode

# Pre-compiled high-confidence regex attack signatures
SQLI_PATTERNS = [
    re.compile(r"('\s*(or|and)\s*['\d\w]+\s*=\s*['\d\w]+)", re.IGNORECASE),
    re.compile(r"(union\s+select|union\s+all\s+select)", re.IGNORECASE),
    re.compile(r"(;\s*(drop|alter|delete|update|insert)\s+table)", re.IGNORECASE),
    re.compile(r"(--|#|/\*.*?\*/)", re.IGNORECASE),
    re.compile(r"(exec\s*\(|xp_cmdshell|benchmark\s*\(|sleep\s*\()", re.IGNORECASE),
]

NOSQLI_PATTERNS = [
    re.compile(r"(\$where|\$regex|\$gt|\$ne|\$lt|\$lte|\$gte|\$in|\$nin|\$expr)", re.IGNORECASE),
    re.compile(r"(\btojson\b|\bthis\.[a-zA-Z0-9_]+)", re.IGNORECASE),
]

XSS_PATTERNS = [
    re.compile(r"(<\s*script\b[^>]*>|javascript\s*:|onerror\s*=|onload\s*=)", re.IGNORECASE),
    re.compile(r"(<\s*img\b[^>]*onerror|document\.cookie|alert\s*\()", re.IGNORECASE),
]

CMD_PATTERNS = [
    re.compile(r"(;\s*(cat|ls|rm|curl|wget|id|whoami|sh|bash)\b)", re.IGNORECASE),
    re.compile(r"(\|\s*(cat|ls|rm|curl|wget|id|whoami|sh|bash)\b)", re.IGNORECASE),
]


class InjectionVisitor(Visitor):
    def __init__(self):
        super().__init__()
        self.sqli_count = 0
        self.nosqli_count = 0
        self.xss_count = 0
        self.cmd_count = 0
        self.injected_strings = []

    def enter_argument(self, node, key, parent, path, ancestors):
        if hasattr(node, 'value') and isinstance(node.value, StringValueNode):
            text = node.value.value
            self._scan_string(text)

    def _scan_string(self, text: str):
        if not text or len(text) < 3:
            return

        for p in SQLI_PATTERNS:
            if p.search(text):
                self.sqli_count += 1
                self.injected_strings.append("sqli")
                break

        for p in NOSQLI_PATTERNS:
            if p.search(text):
                self.nosqli_count += 1
                self.injected_strings.append("nosqli")
                break

        for p in XSS_PATTERNS:
            if p.search(text):
                self.xss_count += 1
                self.injected_strings.append("xss")
                break

        for p in CMD_PATTERNS:
            if p.search(text):
                self.cmd_count += 1
                self.injected_strings.append("cmdi")
                break


def extract_injection_features(ast: DocumentNode, variables: Dict[str, Any] = None) -> dict:
    """Scan GraphQL AST string arguments and input variables for injection payloads."""
    visitor = InjectionVisitor()
    visit(ast, visitor)

    # Also scan variables if present
    if variables and isinstance(variables, dict):
        for v in variables.values():
            if isinstance(v, str):
                visitor._scan_string(v)

    total_injection_count = (
        visitor.sqli_count + visitor.nosqli_count + visitor.xss_count + visitor.cmd_count
    )

    return {
        "injection_score": min(1.0, total_injection_count * 0.5),
        "sqli_detected": 1 if visitor.sqli_count > 0 else 0,
        "nosqli_detected": 1 if visitor.nosqli_count > 0 else 0,
        "xss_detected": 1 if visitor.xss_count > 0 else 0,
        "cmd_detected": 1 if visitor.cmd_count > 0 else 0,
    }
