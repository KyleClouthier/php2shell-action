# PHP2Shell Check (GitHub Action)

[![GitHub Marketplace](https://img.shields.io/badge/Marketplace-PHP2Shell%20Check-2ea44f?logo=github)](https://github.com/marketplace/actions/php2shell-check)
[![self-test](https://github.com/KyleClouthier/php2shell-action/actions/workflows/test.yml/badge.svg)](https://github.com/KyleClouthier/php2shell-action/actions/workflows/test.yml)
![PHP2Shell](https://img.shields.io/badge/PHP2Shell-CVSS%209.2-e5534b) ![MIT](https://img.shields.io/badge/licence-MIT-blue)

Fail the build if your project runs or pins a PHP version without the PHP2Shell fix.

On 21 October 2026 PHP released emergency fixes for two critical flaws (PHP2Shell) that can let an attacker run code
on a server without logging in. Fixed releases: **8.5.12, 8.4.27, 8.3.36, 8.2.35**. PHP 8.1 and older got **no
release**, only source backports. Updating your framework does not fix it; the flaw is in PHP itself.

This Action finds every place your repository sets a PHP version and flags the ones without the fix, right on the
line in your pull request.

## Usage

```yaml
name: PHP2Shell
on: [push, pull_request]
jobs:
  php2shell:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: KyleClouthier/php2shell-action@v1
```

## What it checks

| Where | Example | Result |
|---|---|---|
| PHP on the runner | `php -r 'echo PHP_VERSION;'` | error if unfixed |
| `composer.json` platform | `"config": {"platform": {"php": "8.1.2"}}` | error if unfixed |
| `composer.json` require | `"php": "^7.4\|^8.0"` | warning: still allows versions with no release |
| Dockerfiles | `FROM php:8.3.10-fpm` | error if unfixed |
| Dockerfiles, floating tags | `FROM php:8.4-apache` | warning: rebuild so it pulls 8.4.27+ |
| `.php-version`, `.tool-versions` | `8.2.30` | error if unfixed |
| Workflows | `php-version: "8.0"` in setup-php | error; old versions in a test matrix are warnings |

It walks the whole repository, so monorepos and modular setups with several `composer.json` files, Dockerfiles or
workflows get every one checked, and the output lists which files it scanned. `vendor/` and `node_modules/` are
skipped. It only reads.

## Inputs and outputs

| Input | Default | |
|---|---|---|
| `path` | `.` | Folder to scan |
| `fail` | `true` | Fail the job when a version without the fix is found |
| `check-runtime` | `true` | Also check the PHP on the runner |

Outputs: `status` (`ok`, `review` or `action-needed`), `errors`, `warnings`. A summary table is added to the job page.

```yaml
      - uses: KyleClouthier/php2shell-action@v1
        id: php2shell
        with:
          fail: false
      - if: steps.php2shell.outputs.status == 'action-needed'
        run: echo "PHP2Shell fix missing somewhere, see the job summary"
```

## Related

- [php2shell-check](https://github.com/KyleClouthier/php2shell-check): a self-deleting file for a live site's exact
  PHP version, and a script that finds every PHP install on a server.
- [Check any live site from the browser](https://simgen.dev/php-patch-check), nothing to install.

Built by Kyle Clouthier ([simgen.dev](https://simgen.dev)). MIT licence. If it helped, a star helps the next team
find it.
