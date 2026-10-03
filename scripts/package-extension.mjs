import { execFileSync } from 'node:child_process'
import { mkdtempSync, mkdirSync, copyFileSync, writeFileSync, rmSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'

const directory = mkdtempSync(path.join(os.tmpdir(), 'rankforge-vsix-'))
try {
  mkdirSync(path.join(directory, 'extension', 'dist'), { recursive: true })
  copyFileSync('extension/package.json', path.join(directory, 'extension', 'package.json'))
  copyFileSync('extension/dist/extension.cjs', path.join(directory, 'extension', 'dist', 'extension.cjs'))
  copyFileSync('README.md', path.join(directory, 'extension', 'README.md'))
  writeFileSync(path.join(directory, '[Content_Types].xml'), '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="json" ContentType="application/json"/><Default Extension="cjs" ContentType="application/javascript"/><Default Extension="md" ContentType="text/markdown"/><Default Extension="vsixmanifest" ContentType="text/xml"/></Types>')
  writeFileSync(path.join(directory, 'extension.vsixmanifest'), '<?xml version="1.0"?><PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011"><Metadata><Identity Language="en-US" Id="rankforge-bridge" Version="0.1.0" Publisher="rankforge"/><DisplayName>Rankforge Workshop</DisplayName><Description xml:space="preserve">A dedicated workshop window for Rankforge.</Description><Properties><Property Id="Microsoft.VisualStudio.Code.Engine" Value="^1.110.0"/></Properties></Metadata><Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation><Dependencies/><Assets><Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/></Assets></PackageManifest>')
  execFileSync('zip', ['-q', '-r', path.resolve('rankforge-workshop-0.1.0.vsix'), '.'], { cwd: directory })
  console.log('Created rankforge-workshop-0.1.0.vsix. Installation is owner-initiated.')
} finally { rmSync(directory, { recursive: true, force: true }) }
