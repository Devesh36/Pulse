class Pulse < Formula
  desc "Evidence-driven incident investigation and approved recovery for local Docker"
  homepage "https://github.com/Devesh36/Pulse"
  license "MIT"
  head "https://github.com/Devesh36/Pulse.git", branch: "work"

  depends_on "python@3.12"
  depends_on "uv"

  def install
    ENV["UV_PROJECT_ENVIRONMENT"] = libexec.to_s
    ENV["UV_NO_CACHE"] = "1"
    system Formula["uv"].opt_bin/"uv", "sync", "--frozen", "--no-dev",
           "--no-editable", "--python", Formula["python@3.12"].opt_bin/"python3.12"
    bin.install_symlink libexec/"bin/pulse"
    bin.install_symlink libexec/"bin/Pulse" unless (bin/"Pulse").exist?
  end

  def caveats
    <<~EOS
      Run: pulse repl
      Docker Desktop or Docker Engine with Compose is required for real demos.
      pulse lab stop retains your demo data; pulse lab down removes lab volumes.
    EOS
  end

  test do
    assert_match "Pulse", shell_output("#{bin}/pulse --version")
    assert_match "repl", shell_output("#{bin}/pulse --help")
    assert_match "Guided crash", pipe_output("#{bin}/Pulse Repl", "help\nexit\n", 0)
  end
end
