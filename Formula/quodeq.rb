class Quodeq < Formula
  include Language::Python::Virtualenv

  desc "AI-powered source code quality evaluation platform"
  homepage "https://github.com/quodeq/quodeq"
  url "https://files.pythonhosted.org/packages/source/q/quodeq/quodeq-0.6.2.tar.gz"
  sha256 "0940d6b62b7329c156b13070a16b1c9d97e113c90e870053225b92af3566b06d"
  license "MIT"

  depends_on "python@3.12"
  depends_on "node"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "quodeq", shell_output("#{bin}/quodeq --help 2>&1", 2)
  end
end
