"""Terminal launcher wrapper for SigmaOS-term
(inspired by ptyxis-minted, omaterm, foot/ghostty/kitty/alacritty).

Principles: one data-driven backend table (DRY -- adding a terminal is a dict
entry), plan/execute separation (argv is built pure; launch is a thin executor
self_test never runs), fail-fast validation of titles, commands, fonts and
keybind syntax, deterministic rendering.
"""
import argparse, re, shlex, subprocess, sys

ENGINE = {
    "name": "sigma-term",
    "summary": "Terminal launcher wrapper: launch plans, profiles, fonts, keybinds",
    "language": "python",
    "verbs": ["launch-plan", "profiles", "font", "keybinds"],
    "principles": ["Separation of Concerns", "Data-Driven Design",
                   "Defensive Programming", "Fail-Fast", "KISS",
                   "Deterministic Testing"],
}

cli_doc = """\
$ sigma-term launch-plan --backend kitty --title dev -- htop
kitty --title=dev -e htop
$ sigma-term launch-plan --backend alacritty --title logs
alacritty -t logs
$ sigma-term profiles
$ sigma-term font --backend foot --family "JetBrainsMono Nerd Font" --size 12
$ sigma-term keybinds --backend kitty --bind new_tab=ctrl+shift+t
"""


class TermError(ValueError):
    pass


# --------------------------------------------------------------------------- #
#  Backend table: argv shape, font line, extras, keybind format
# --------------------------------------------------------------------------- #
def _font_foot(s):    return f"font={s['family']}:size={s['size']}"
def _font_kitty(s):   return (f"font_family {s['family']}\n"
                              f"font_size {s['size']}")
def _font_ghostty(s): return (f"font-family = {s['family']}\n"
                              f"font-size = {s['size']}")
def _font_alacritty(s): return (f"family = \"{s['family']}\"  "
                                f"# size {s['size']}")
def _font_ptyxis(s):  return (f"font={s['family']}\n"
                              f"font-size={s['size']}")
def _font_omaterm(s): return f"font = {s['family']} {s['size']}"


def _extra_foot(p):    return f"alpha={p['opacity']}\nscrollback-lines=10000\n"
def _extra_kitty(p):   return f"background_opacity {p['opacity']}\n"
def _extra_ghostty(p): return f"background-opacity = {p['opacity']}\n"
def _extra_alacritty(p): return f"[window]\nopacity = {p['opacity']}\n"
def _extra_ptyxis(p):  return f"opacity={p['opacity']}\n"
def _extra_omaterm(p): return f"opacity = {p['opacity']}\n"


BACKENDS = {
    "foot":      {"bin": "foot",      "title": ("--title={t}",), "sep": "--",
                  "font": _font_foot, "extra": _extra_foot,
                  "keyfmt": "keyboard-bindings = {key}={action}"},
    "ghostty":   {"bin": "ghostty",   "title": ("--title={t}",), "sep": "-e",
                  "font": _font_ghostty, "extra": _extra_ghostty,
                  "keyfmt": "bind = {key}={action}"},
    "kitty":     {"bin": "kitty",     "title": ("--title={t}",), "sep": "-e",
                  "font": _font_kitty, "extra": _extra_kitty,
                  "keyfmt": "map {key} {action}"},
    "alacritty": {"bin": "alacritty", "title": ("-t", "{t}"), "sep": "-e",
                  "font": _font_alacritty, "extra": _extra_alacritty,
                  "keyfmt": "\"{akey}\": \"{action}\","},
    "ptyxis":    {"bin": "ptyxis",    "title": ("--title={t}",), "sep": "--",
                  "font": _font_ptyxis, "extra": _extra_ptyxis,
                  "keyfmt": "keybind {key} {action}"},
    "omaterm":   {"bin": "omaterm",   "title": ("--title={t}",), "sep": "--",
                  "font": _font_omaterm, "extra": _extra_omaterm,
                  "keyfmt": "bind {key} = {action}"},
}

PROFILES = {
    "default": {"opacity": 1.0, "font_size": 12, "desc": "stock look"},
    "dim":     {"opacity": 0.9, "font_size": 12, "desc": "slightly transparent"},
    "compact": {"opacity": 1.0, "font_size": 10, "desc": "small type"},
    "big":     {"opacity": 1.0, "font_size": 16, "desc": "accessibility"},
}

DEFAULT_FONT = "JetBrainsMono Nerd Font"


def _backend(name):
    if name not in BACKENDS:
        raise TermError(f"unknown backend {name!r} "
                        f"(have: {', '.join(sorted(BACKENDS))})")
    return BACKENDS[name]


# --------------------------------------------------------------------------- #
#  Launch plan (pure argv)
# --------------------------------------------------------------------------- #
def launch_plan(backend, title="sigma", cmd=None, cwd=None):
    spec = _backend(backend)
    if not isinstance(title, str) or not title.strip() or "\n" in title:
        raise TermError(f"bad title: {title!r}")
    argv = [spec["bin"]] + [p.format(t=title) for p in spec["title"]]
    if cmd:
        if isinstance(cmd, str):
            raise TermError("cmd must be a list of argv items, not a string")
        for item in cmd:
            if not isinstance(item, str) or not item or "\n" in item or "\x00" in item:
                raise TermError(f"bad command item: {item!r}")
        argv += [spec["sep"]] + list(cmd)
    if cwd is not None and (not isinstance(cwd, str) or "\x00" in cwd
                            or "\n" in cwd or not cwd.strip()):
        raise TermError(f"bad cwd: {cwd!r}")
    return {"backend": backend, "argv": argv, "cwd": cwd,
            "title": title, "cmd": list(cmd) if cmd else []}


def execute(plan, **popen_kw):
    """THIN side-effecting layer: run the terminal. Never self-tested."""
    return subprocess.run(plan["argv"], cwd=plan.get("cwd"), **popen_kw)


# --------------------------------------------------------------------------- #
#  Profiles / fonts (pure config text)
# --------------------------------------------------------------------------- #
def profiles():
    return dict(PROFILES)


def font_spec(family, size):
    if not isinstance(family, str) or not family.strip():
        raise TermError("empty font family")
    if "\n" in family or "\x00" in family:
        raise TermError("font family must be a single line")
    if not isinstance(size, int) or isinstance(size, bool) or not 6 <= size <= 72:
        raise TermError(f"font size must be an integer in 6..72, got {size!r}")
    return {"family": family.strip(), "size": size}


def render_font(backend, family, size):
    spec = _backend(backend)
    return spec["font"](font_spec(family, size))


def render_profile(backend, profile, font=DEFAULT_FONT, font_size=None):
    spec = _backend(backend)
    if profile not in PROFILES:
        raise TermError(f"unknown profile {profile!r} "
                        f"(have: {', '.join(sorted(PROFILES))})")
    p = PROFILES[profile]
    size = p["font_size"] if font_size is None else font_size
    f = font_spec(font, size)
    return (f"# sigma-term profile={profile} backend={backend}\n"
            + spec["font"](f) + "\n" + spec["extra"](p))


# --------------------------------------------------------------------------- #
#  Keybinds (parse, normalise, render)
# --------------------------------------------------------------------------- #
_MODS = ("ctrl", "alt", "shift", "super")
_KEYS = {"enter", "escape", "tab", "space", "backspace", "delete", "insert",
         "up", "down", "left", "right", "page_up", "page_down", "home", "end"}
_KEYS |= {f"f{i}" for i in range(1, 25)}
_ACTION_RE = re.compile(r"^[A-Za-z0-9_:.+-]+$")


def parse_keybind(spec):
    """'SHIFT+CTRL+t' -> canonical 'ctrl+shift+t'. Fail-fast on nonsense."""
    if not isinstance(spec, str) or not spec.strip():
        raise TermError(f"bad keybind: {spec!r}")
    parts = [p.strip().lower() for p in spec.strip().split("+")]
    if any(not p for p in parts):
        raise TermError(f"bad keybind: {spec!r}")
    key, mods = parts[-1], parts[:-1]
    for m in mods:
        if m not in _MODS:
            raise TermError(f"unknown modifier {m!r} in {spec!r}")
    if len(set(mods)) != len(mods):
        raise TermError(f"duplicate modifier in {spec!r}")
    if key in _MODS:
        raise TermError(f"missing key in {spec!r}")
    plain = len(key) == 1 and key.isascii() and key.isalnum()
    if not plain and key not in _KEYS:
        raise TermError(f"unknown key {key!r} in {spec!r}")
    ordered = [m for m in _MODS if m in mods]
    return "+".join(ordered + [key])


def style_key(key, style="lower"):
    parsed = parse_keybind(key)
    if style == "lower":
        return parsed
    if style == "alacritty":
        return "+".join(part.title() for part in parsed.split("+"))
    raise TermError(f"unknown key style {style!r}")


def keybinds(backend, bindings):
    """bindings: list of (action, key). Renders one config line each."""
    spec = _backend(backend)
    seen, out = {}, []
    for action, key in bindings:
        if not isinstance(action, str) or not _ACTION_RE.match(action):
            raise TermError(f"bad action: {action!r}")
        parsed = parse_keybind(key)
        if parsed in seen:
            raise TermError(
                f"duplicate keybind {parsed}: {seen[parsed]!r} vs {action!r}")
        seen[parsed] = action
        out.append(spec["keyfmt"].format(key=parsed, akey=style_key(parsed, "alacritty"),
                                         action=action))
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=ENGINE["name"], description=ENGINE["summary"])
    sub = p.add_subparsers(dest="cmd", required=True)
    lp = sub.add_parser("launch-plan", help="build the terminal argv")
    lp.add_argument("--backend", required=True, choices=sorted(BACKENDS))
    lp.add_argument("--title", default="sigma")
    lp.add_argument("--cwd", default=None)
    lp.add_argument("command", nargs="*", help="command to run (after --)")
    pf = sub.add_parser("profiles", help="list known profiles")
    pf.add_argument("--backend", default=None, choices=sorted(BACKENDS))
    fo = sub.add_parser("font", help="render a font line for a backend")
    fo.add_argument("--backend", required=True, choices=sorted(BACKENDS))
    fo.add_argument("--family", default=DEFAULT_FONT)
    fo.add_argument("--size", type=int, default=12)
    kb = sub.add_parser("keybinds", help="render keybinding config lines")
    kb.add_argument("--backend", required=True, choices=sorted(BACKENDS))
    kb.add_argument("--bind", action="append", required=True,
                    metavar="ACTION=KEY", help="repeatable")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "launch-plan":
            plan = launch_plan(args.backend, args.title, args.command or None,
                               args.cwd)
            print(shlex.join(plan["argv"]))
        elif args.cmd == "profiles":
            for name, p in sorted(PROFILES.items()):
                if args.backend:
                    text = render_profile(args.backend, name)
                    print(f"{name}\t{p['desc']}\t"
                          f"({' / '.join(text.splitlines()[1:2])})")
                else:
                    print(f"{name}\t{p['desc']}\t"
                          f"opacity={p['opacity']} size={p['font_size']}")
        elif args.cmd == "font":
            print(render_font(args.backend, args.family, args.size))
        elif args.cmd == "keybinds":
            pairs = []
            for item in args.bind:
                if "=" not in item:
                    raise TermError(f"--bind wants ACTION=KEY: {item!r}")
                action, key = item.split("=", 1)
                pairs.append((action, key))
            for line in keybinds(args.backend, pairs):
                print(line)
        return 0
    except TermError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def self_test() -> None:
    # --- launch plans per backend ------------------------------------------
    kitty = launch_plan("kitty", "dev", ["htop"])
    assert kitty["argv"] == ["kitty", "--title=dev", "-e", "htop"], kitty["argv"]
    foot = launch_plan("foot", "dev", ["htop"])
    assert foot["argv"] == ["foot", "--title=dev", "--", "htop"]
    al = launch_plan("alacritty", "logs", ["tail", "-f", "/var/log/syslog"])
    assert al["argv"] == ["alacritty", "-t", "logs", "-e", "tail", "-f",
                          "/var/log/syslog"], al["argv"]
    gh = launch_plan("ghostty", "dev")
    assert gh["argv"] == ["ghostty", "--title=dev"]  # no command -> no separator
    assert launch_plan("ptyxis", "x", ["nvim"])["argv"][-2:] == ["--", "nvim"]
    assert launch_plan("omaterm", "x", ["nvim"])["argv"][-2:] == ["--", "nvim"]
    plan = launch_plan("kitty", "dev", ["htop"], cwd="/tmp/work")
    assert plan["cwd"] == "/tmp/work"
    for bad_call in ((launch_plan, ("wezterm", "x")),
                     (launch_plan, ("kitty", "a\nb")),
                     (launch_plan, ("kitty", "x", "htop")),          # str cmd
                     (launch_plan, ("kitty", "x", ["a\x00b"])),
                     (launch_plan, ("kitty", "x", ["ok"], "bad\ncwd")),
                     (launch_plan, ("kitty", "  "))):
        try:
            bad_call[0](*bad_call[1])
        except TermError:
            pass
        else:
            raise AssertionError(f"should have rejected: {bad_call}")

    # --- profiles -----------------------------------------------------------
    assert sorted(profiles()) == ["big", "compact", "default", "dim"]
    for backend in BACKENDS:
        text = render_profile(backend, "dim")
        assert text.startswith(f"# sigma-term profile=dim backend={backend}")
        assert str(PROFILES["dim"]["font_size"]) in text
        assert "0.9" in text
        assert text == render_profile(backend, "dim")  # deterministic
    kitty_txt = render_profile("kitty", "dim")
    assert "font_family JetBrainsMono Nerd Font" in kitty_txt
    assert "font_size 12" in kitty_txt and "background_opacity 0.9" in kitty_txt
    foot_txt = render_profile("foot", "dim")
    assert "font=JetBrainsMono Nerd Font:size=12" in foot_txt
    assert "alpha=0.9" in foot_txt
    gh_txt = render_profile("ghostty", "big")
    assert "font-size = 16" in gh_txt and "background-opacity = 1.0" in gh_txt
    al_txt = render_profile("alacritty", "compact")
    assert "[window]" in al_txt and "opacity = 1.0" in al_txt
    assert 'family = "JetBrainsMono Nerd Font"' in al_txt
    try:
        render_profile("kitty", "neon")
    except TermError:
        pass
    else:
        raise AssertionError("unknown profile not rejected")

    # --- font validation ----------------------------------------------------
    assert render_font("kitty", "Fira Code", 14) == "font_family Fira Code\nfont_size 14"
    assert render_font("foot", "Fira Code", 14) == "font=Fira Code:size=14"
    for bad_call in ((render_font, ("kitty", "", 12)),
                     (render_font, ("kitty", "Fira\nCode", 12)),
                     (render_font, ("kitty", "Fira", 3)),
                     (render_font, ("kitty", "Fira", 100)),
                     (render_font, ("kitty", "Fira", "12"))):
        try:
            bad_call[0](*bad_call[1])
        except TermError:
            pass
        else:
            raise AssertionError(f"should have rejected: {bad_call}")

    # --- keybind parsing / normalisation ------------------------------------
    assert parse_keybind("ctrl+shift+t") == "ctrl+shift+t"
    assert parse_keybind("SHIFT+CTRL+T") == "ctrl+shift+t"
    assert parse_keybind("Super+Space") == "super+space"
    assert parse_keybind("escape") == "escape"
    assert parse_keybind("alt+f4") == "alt+f4"
    assert style_key("ctrl+shift+t", "alacritty") == "Ctrl+Shift+T"
    for bad in ("ctrl+shift", "meta+a", "ctrl+ctrl+t", "ctrl+", "",
                "ctrl+shift+f25", "ctrl+ab", "+x"):
        try:
            parse_keybind(bad)
        except TermError:
            pass
        else:
            raise AssertionError(f"keybind should have been rejected: {bad!r}")

    # --- keybind rendering --------------------------------------------------
    lines = keybinds("kitty", [("new_tab", "ctrl+shift+t"), ("close", "ctrl+w")])
    assert lines == ["map ctrl+shift+t new_tab", "map ctrl+w close"], lines
    assert keybinds("ghostty", [("new_tab", "ctrl+shift+t")]) == \
        ["bind = ctrl+shift+t=new_tab"]
    assert keybinds("alacritty", [("new_tab", "shift+ctrl+t")]) == \
        ['"Ctrl+Shift+T": "new_tab",']
    try:
        keybinds("kitty", [("new_tab", "ctrl+shift+t"),
                           ("zoom", "SHIFT+CTRL+T")])  # normalises to the same
    except TermError:
        pass
    else:
        raise AssertionError("duplicate (normalised) keybind not caught")
    try:
        keybinds("kitty", [("bad action!", "ctrl+w")])
    except TermError:
        pass
    else:
        raise AssertionError("bad action not rejected")
    try:
        keybinds("wezterm", [("close", "ctrl+w")])
    except TermError:
        pass
    else:
        raise AssertionError("unknown backend not rejected")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
