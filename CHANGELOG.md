# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-06-13

### Added
- Initial release.
- Synchronous `IppClient` and asynchronous `AsyncIppClient`.
- Sans-IO IPP/IPPS codec (RFC 8010) with full request encoding and response
  decoding, including nested collections.
- IPP operation set (RFC 8011) with the IANA operation registry through 0x46.
- Print-Job submission, verified end to end against real hardware
  (HP Color LaserJet Pro M283fdw over IPPS).
- TLS support with certificate fingerprint pinning, configurable verification,
  and legacy-cipher (SECLEVEL) handling for older printers.
- Distinct exception taxonomy (`IppDecodeError`, `IppResponseError`,
  `IppHttpError`, `FingerprintMismatch`).
- Typed API shipping `py.typed`, checked under strict mypy.

[Unreleased]: https://github.com/smck83/ippx/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/smck83/ippx/releases/tag/v0.1.0
