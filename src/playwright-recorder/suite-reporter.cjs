const { writeFileSync, renameSync } = require('node:fs');
const { basename } = require('node:path');

const secrets = [...new Set(JSON.parse(process.env.TESTAIZE_SUITE_SECRETS || '[]').filter(Boolean)
  .flatMap((value) => [value, JSON.stringify(value).slice(1, -1)]))].sort((a, b) => b.length - a.length);
function safe(value) {
  let text = String(value || '').replace(/\x1b\[[0-9;]*m/g, '');
  for (const secret of secrets) text = text.split(secret).join('[secret]');
  return text;
}

class SuiteReporter {
  constructor() { this.report = { state: 'running', total: 0, passed: 0, failed: 0, skipped: 0, results: [], errors: [] }; }
  publish() {
    const target = process.env.TESTAIZE_SUITE_REPORT;
    writeFileSync(target + '.node.tmp', JSON.stringify(this.report));
    renameSync(target + '.node.tmp', target);
  }
  onBegin(_config, suite) { this.report.total = suite.allTests().length; this.publish(); }
  onTestBegin(test) { this.report.current = safe(test.title); this.publish(); }
  onTestEnd(test, result) {
    const status = result.status === 'skipped' ? 'skipped' : result.status === test.expectedStatus ? 'passed' : 'failed';
    this.report[status]++;
    this.report.results.push({ script_id: basename(test.location.file).replace(/\.spec\.ts$/, ''), title: safe(test.titlePath().slice(2).join(' › ') || test.title),
      status, duration: result.duration, error: safe(result.errors.map((error) => error.message || error.value || '').join('\n')) });
    this.publish();
  }
  onError(error) { this.report.errors.push(safe(error.message || error.value)); this.publish(); }
  onEnd() { this.report.state = this.report.errors.length && !this.report.total ? 'error' : 'completed'; this.report.current = ''; this.publish(); }
  printsToStdio() { return false; }
}
module.exports = SuiteReporter;
