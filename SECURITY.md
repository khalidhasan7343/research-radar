# Security policy

## Supported versions

Security fixes are made on the latest release only.

## Reporting a vulnerability

Please do not open a public issue. Report it privately, either through GitHub
(*Security > Report a vulnerability* on the repository page) or by email to
<mdkhalidhasan7343@gmail.com>. Include the steps to reproduce and the version
you used.

## Things to know when running Research Radar

- `radar serve` has no authentication. It listens on `127.0.0.1` by default;
  do not bind it to a public address (`--host 0.0.0.0`) on a machine others can
  reach.
- `radar.toml` and the `RADAR_*` environment variables can hold API keys and
  your email address. Keep them out of version control.
- The database in `data/` contains paper abstracts. Do not publish it.
