class Quodeq < Formula
  include Language::Python::Virtualenv

  desc "AI-powered source code quality evaluation platform"
  homepage "https://github.com/quodeq/quodeq"
  url "https://files.pythonhosted.org/packages/source/q/quodeq/quodeq-0.4.0.tar.gz"
  sha256 "1aa6df2cbdcefb9761bf712cc48cd18015e091ca6589d1db917f1725f5727d94"
  license "MIT"

  depends_on "python@3.12"
  depends_on "node"

  def install
    # Build the web UI before installing the Python package
    cd "ui/web" do
      system "npm", "install", *std_npm_args(prefix: false)
      system "npm", "run", "build"
    end

    # Bundle pre-built static assets into the package
    cp_r "ui/web/dist/.", "src/quodeq/static"

    virtualenv_install_with_resources
  end

  test do
    assert_match "quodeq", shell_output("#{bin}/quodeq --help 2>&1", 2)
  end
end
