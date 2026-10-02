"""Fetch and score the public, visible signals on a candidate portfolio site."""

from html.parser import HTMLParser
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests


MAX_PAGE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5
REQUEST_TIMEOUT = (4, 10)


class PortfolioAuditError(ValueError):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


class _PortfolioHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text_parts = []
        self.headings = []
        self.links = []
        self.project_container_count = 0
        self.image_count = 0
        self.images_with_alt = 0
        self.has_email_field = False
        self.has_phone_field = False
        self.has_contact_form = False
        self.title = ""
        self.description = ""
        self._in_title = False
        self._heading_tag = None
        self._heading_parts = []
        self._anchor = None
        self._ignored_tags = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style", "noscript", "template"}:
            self._ignored_tags += 1
        elif self._ignored_tags:
            return
        elif tag == "title":
            self._in_title = True
        elif tag in {"h1", "h2", "h3", "h4"}:
            self._heading_tag = tag
            self._heading_parts = []
        elif tag == "meta" and attrs.get("name", "").lower() == "description":
            self.description = attrs.get("content", "").strip()
        elif tag == "a":
            self._anchor = {"href": attrs.get("href", ""), "text": []}
        elif tag == "img":
            self.image_count += 1
            if attrs.get("alt", "").strip():
                self.images_with_alt += 1
        elif tag == "input":
            input_type = attrs.get("type", "").lower()
            field_marker = " ".join(
                (attrs.get("name", ""), attrs.get("id", ""), attrs.get("placeholder", ""))
            ).lower()
            self.has_email_field = self.has_email_field or input_type == "email" or "email" in field_marker
            self.has_phone_field = self.has_phone_field or input_type == "tel" or "phone" in field_marker
        elif tag == "form":
            form_marker = " ".join(
                (
                    attrs.get("action", ""),
                    attrs.get("id", ""),
                    attrs.get("class", ""),
                    attrs.get("name", ""),
                    attrs.get("aria-label", ""),
                )
            ).lower()
            self.has_contact_form = self.has_contact_form or bool(
                re.search(r"\b(contact|message|reach)\b", form_marker)
            )
        elif tag in {"article", "li", "div"}:
            marker = " ".join((attrs.get("class", ""), attrs.get("id", ""))).lower()
            is_project_marker = re.search(r"\b(project|portfolio|case-study|case_study)\b", marker)
            is_card = re.search(r"\b(card|item|entry|case-study|case_study)\b", marker)
            if is_project_marker and (tag in {"article", "li"} or is_card):
                self.project_container_count += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "template"} and self._ignored_tags:
            self._ignored_tags -= 1
            return
        if self._ignored_tags:
            return
        if tag == "title":
            self._in_title = False
        elif tag == self._heading_tag:
            heading = " ".join(" ".join(self._heading_parts).split())
            if heading:
                self.headings.append((tag, heading))
            self._heading_tag = None
            self._heading_parts = []
        elif tag == "a" and self._anchor is not None:
            text = " ".join(" ".join(self._anchor["text"]).split())
            self.links.append((self._anchor["href"].strip(), text))
            self._anchor = None

    def handle_data(self, data):
        if self._ignored_tags:
            return
        text = data.strip()
        if not text:
            return
        self.text_parts.append(text)
        if self._in_title:
            self.title += f" {text}"
        if self._heading_tag:
            self._heading_parts.append(text)
        if self._anchor is not None:
            self._anchor["text"].append(text)


def _validated_public_url(value: str) -> str:
    value = value.strip()
    if not value:
        raise PortfolioAuditError("Enter a portfolio website URL.")
    if "://" not in value:
        value = f"https://{value}"

    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as exc:
        raise PortfolioAuditError("Enter a valid portfolio website URL.") from exc

    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise PortfolioAuditError("Portfolio URL must use http or https.")
    if parts.username or parts.password:
        raise PortfolioAuditError("Portfolio URL must not include login credentials.")
    if port not in {None, 80, 443}:
        raise PortfolioAuditError("Portfolio URL must use the standard HTTP or HTTPS port.")

    host = parts.hostname.rstrip(".")
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(result[4][0])
                for result in socket.getaddrinfo(host, port or (443 if parts.scheme == "https" else 80))
            }
        except (OSError, ValueError) as exc:
            raise PortfolioAuditError("Portfolio website hostname could not be resolved.", 502) from exc

    if not addresses or any(not address.is_global for address in addresses):
        raise PortfolioAuditError("Portfolio URL must resolve to a public website.")

    return urlunsplit((parts.scheme.lower(), parts.netloc, parts.path or "/", parts.query, ""))


def _fetch_html(url: str) -> tuple[str, str]:
    current_url = url
    for redirect_count in range(MAX_REDIRECTS + 1):
        current_url = _validated_public_url(current_url)
        try:
            response = requests.get(
                current_url,
                headers={"User-Agent": "TalentAI-Portfolio-Audit/1.0", "Accept": "text/html"},
                timeout=REQUEST_TIMEOUT,
                stream=True,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise PortfolioAuditError("Could not reach the portfolio website.", 502) from exc

        try:
            if response.is_redirect:
                location = response.headers.get("Location")
                if not location or redirect_count >= MAX_REDIRECTS:
                    raise PortfolioAuditError("Portfolio website redirected too many times.", 502)
                current_url = urljoin(current_url, location)
                continue
            if response.status_code != 200:
                raise PortfolioAuditError(
                    f"Portfolio website returned HTTP {response.status_code}.",
                    502,
                )

            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                raise PortfolioAuditError("Portfolio link does not return an HTML page.", 422)

            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_PAGE_BYTES:
                raise PortfolioAuditError("Portfolio page is too large to audit (limit 2 MB).", 422)

            body = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                body.extend(chunk)
                if len(body) > MAX_PAGE_BYTES:
                    raise PortfolioAuditError("Portfolio page is too large to audit (limit 2 MB).", 422)
            encoding = response.encoding or "utf-8"
            return current_url, bytes(body).decode(encoding, errors="replace")
        except requests.RequestException as exc:
            raise PortfolioAuditError("Could not read the portfolio website.", 502) from exc
        finally:
            response.close()

    raise PortfolioAuditError("Portfolio website redirected too many times.", 502)


def audit_portfolio_site(portfolio_url: str, candidate_name: str, candidate_email: str | None = None) -> dict:
    """Fetch a public page and score explicit portfolio completeness signals."""
    normalized_url, html = _fetch_html(portfolio_url)
    parser = _PortfolioHTMLParser()
    parser.feed(html)

    text = " ".join(parser.text_parts)
    lower_text = text.lower()
    heading_text = [heading.lower() for _, heading in parser.headings]
    link_text = [(href.lower(), label.lower()) for href, label in parser.links]

    def section_text_at(index):
        section_heading = heading_text[index]
        section_start = lower_text.find(section_heading)
        if section_start < 0:
            return ""
        section_level = int(parser.headings[index][0][1])
        section_end = len(text)
        for tag, heading in parser.headings[index + 1:]:
            if int(tag[1]) <= section_level:
                next_heading = lower_text.find(heading.lower(), section_start + len(section_heading))
                if next_heading >= 0:
                    section_end = min(section_end, next_heading)
        return text[section_start + len(section_heading):section_end]

    project_section_index = next(
        (i for i, heading in enumerate(heading_text) if re.search(r"\b(projects?|selected work|portfolio)\b", heading)),
        None,
    )
    has_project_section = project_section_index is not None
    project_headings = []
    if project_section_index is not None:
        project_level = int(parser.headings[project_section_index][0][1])
        for tag, heading in parser.headings[project_section_index + 1:]:
            level = int(tag[1])
            if level <= project_level:
                break
            if not re.search(r"\b(projects?|selected work|portfolio)\b", heading, re.I):
                project_headings.append(heading)
    project_text = section_text_at(project_section_index) if project_section_index is not None else ""
    project_count = max(parser.project_container_count, len(project_headings))
    about_section_index = next(
        (i for i, heading in enumerate(heading_text) if re.search(r"\b(about|bio|profile|who i am)\b", heading)),
        None,
    )
    about_heading = about_section_index is not None
    has_email = (
        bool(re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text))
        or any(href.startswith("mailto:") for href, _ in link_text)
        or parser.has_email_field
    )
    if candidate_email:
        has_email = has_email or candidate_email.lower() in lower_text
    has_phone = (
        bool(re.search(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)", text))
        or parser.has_phone_field
        or any(href.startswith("tel:") for href, _ in link_text)
    )
    has_contact_section = any(
        re.search(r"\b(contact|reach me|get in touch)\b", heading) for heading in heading_text
    ) or any(
        "#contact" in href or re.search(r"\b(contact|email|message)\b", label)
        for href, label in link_text
    ) or parser.has_contact_form
    has_name = bool(candidate_name.strip()) and candidate_name.strip().lower() in lower_text
    about_description = about_heading and len(section_text_at(about_section_index).split()) >= 25
    has_project_description = project_count > 0 and len(project_text.split()) >= 30
    has_technology_details = bool(
        re.search(r"\b(tech stack|technologies|built with|tools used)\b", project_text.lower())
    )
    has_source_link = any(
        "github.com/" in href or re.search(r"\b(source|code|github)\b", label)
        for href, label in link_text
    )
    has_demo_link = any(
        re.search(r"\b(live demo|demo|live site|visit site|deployed)\b", label)
        for _, label in link_text
    )
    has_github_link = any("github.com/" in href for href, _ in link_text)
    has_linkedin_link = any("linkedin.com/" in href for href, _ in link_text)

    checks = [
        {"category": "Contact", "label": "Candidate name is visible", "points": 5 if has_name else 0, "max_points": 5, "passed": has_name},
        {"category": "Contact", "label": "Email address is visible or linked", "points": 10 if has_email else 0, "max_points": 10, "passed": has_email},
        {"category": "Contact", "label": "Phone number or contact section is present", "points": 5 if has_phone or has_contact_section else 0, "max_points": 5, "passed": has_phone or has_contact_section},
        {"category": "About", "label": "About/profile section is present", "points": 5 if about_heading else 0, "max_points": 5, "passed": about_heading},
        {"category": "About", "label": "Page contains a meaningful profile description", "points": 10 if about_description else 0, "max_points": 10, "passed": about_description},
        {"category": "Projects", "label": "Projects/work section is identified", "points": 5 if has_project_section else 0, "max_points": 5, "passed": has_project_section},
        {"category": "Projects", "label": "At least one project is listed", "points": 6 if project_count >= 1 else 0, "max_points": 6, "passed": project_count >= 1, "detail": f"{project_count} project entries detected"},
        {"category": "Projects", "label": "At least two projects are listed", "points": 6 if project_count >= 2 else 0, "max_points": 6, "passed": project_count >= 2},
        {"category": "Projects", "label": "Three or more projects are listed", "points": 8 if project_count >= 3 else 0, "max_points": 8, "passed": project_count >= 3},
        {"category": "Project details", "label": "Project content includes descriptive detail", "points": 10 if has_project_description else 0, "max_points": 10, "passed": has_project_description},
        {"category": "Project details", "label": "Technology/stack information is shown", "points": 5 if has_technology_details else 0, "max_points": 5, "passed": has_technology_details},
        {"category": "Project details", "label": "Source code or a live demo is linked", "points": 5 if has_source_link or has_demo_link else 0, "max_points": 5, "passed": has_source_link or has_demo_link},
        {"category": "Professional links", "label": "GitHub profile is linked", "points": 5 if has_github_link else 0, "max_points": 5, "passed": has_github_link},
        {"category": "Professional links", "label": "LinkedIn profile is linked", "points": 5 if has_linkedin_link else 0, "max_points": 5, "passed": has_linkedin_link},
        {"category": "Page basics", "label": "Page title is present", "points": 3 if parser.title.strip() else 0, "max_points": 3, "passed": bool(parser.title.strip())},
        {"category": "Page basics", "label": "Meta description is present", "points": 3 if parser.description else 0, "max_points": 3, "passed": bool(parser.description)},
        {"category": "Page basics", "label": "Main heading is present", "points": 2 if any(tag == "h1" for tag, _ in parser.headings) else 0, "max_points": 2, "passed": any(tag == "h1" for tag, _ in parser.headings)},
        {"category": "Page basics", "label": "Images include alternative text", "points": 2 if parser.image_count == 0 or parser.images_with_alt == parser.image_count else 0, "max_points": 2, "passed": parser.image_count == 0 or parser.images_with_alt == parser.image_count},
    ]
    categories = {}
    for check in checks:
        category = check["category"]
        summary = categories.setdefault(category, {"score": 0, "max_score": 0})
        summary["score"] += check["points"]
        summary["max_score"] += check["max_points"]

    score = sum(check["points"] for check in checks)
    strengths = [check["label"] for check in checks if check["passed"]]
    weaknesses = [check["label"] for check in checks if not check["passed"]]

    return {
        "portfolio_url": normalized_url,
        "overall_score": score,
        "category_scores": categories,
        "checks": checks,
        "strengths": strengths,
        "weaknesses": weaknesses,
    }
