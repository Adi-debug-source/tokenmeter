class Tokenmeter < Formula
  desc "What your AI coding would cost at API rates"
  homepage "https://github.com/Adi-debug-source/tokenmeter"
  url "https://github.com/Adi-debug-source/tokenmeter/archive/refs/tags/v1.1.1.tar.gz"
  sha256 "a9a9b3b03c9bca9e135b158b75c6e4aac41e32851f47dd4abed5e77983c3c22e"
  license "MIT"

  depends_on macos: :monterey

  def install
    # The formula itself lives in this repository; it has no use once installed.
    libexec.install Dir["*"] - ["Formula"]

    # One engine for every face: the terminal, the menu bar and the status
    # line all run the copy tokenmeter-setup puts in ~/.claude/tools, so an
    # upgrade can never leave two versions pricing the same history.
    (bin/"tokenmeter").write <<~SH
      #!/bin/bash
      ENGINE="$HOME/.claude/tools/tokenmeter/tokenmeter.py"
      if [ ! -f "$ENGINE" ]; then
        echo "Tokenmeter is installed but not set up yet. Run: tokenmeter-setup" >&2
        exit 1
      fi
      SET_UP="$(sed -n 's/^__version__ = "\\(.*\\)"$/\\1/p' "$ENGINE" | head -1)"
      if [ "$SET_UP" != "#{version}" ]; then
        echo "note: Homebrew has Tokenmeter #{version} but $SET_UP is set up." >&2
        echo "      Run tokenmeter-setup to bring the menu bar and status line up to date." >&2
      fi
      exec python3 "$ENGINE" "$@"
    SH

    # The same install.sh a git clone uses, run from Homebrew's copy.
    (bin/"tokenmeter-setup").write <<~SH
      #!/bin/bash
      exec "#{libexec}/install.sh" "$@"
    SH

    chmod 0755, [bin/"tokenmeter", bin/"tokenmeter-setup"]
  end

  def caveats
    <<~EOS
      To finish, run:
        tokenmeter-setup

      It installs the engine, the menu bar app and, if you use Claude Code,
      the /tokenmeter command and the status line. Homebrew cannot write to
      your home folder itself, which is why this is a second step.

      Run it again after `brew upgrade tokenmeter`. To remove Tokenmeter:
        tokenmeter-setup --uninstall
        brew uninstall tokenmeter
    EOS
  end

  test do
    assert_match version.to_s, shell_output("/usr/bin/python3 #{libexec}/tokenmeter.py --version")
    system "/usr/bin/python3", libexec/"tests/test_tokenmeter.py"
  end
end
