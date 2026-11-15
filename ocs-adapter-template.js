/**
 * OCS 어댑터 뼈대 (병원 내부망 서버용)
 * ------------------------------------------------------------------
 * er-ocs-workflow.html 시뮬레이터의 ADAPTERS와 같은 함수 이름을 씁니다.
 * 시뮬레이터 어댑터는 메시지를 "만들어 로그에 남기기"만 하고,
 * 이 파일의 어댑터는 같은 이름의 함수에서 실제로 보내고 받습니다.
 *
 * 주의
 *  - 실제 실행 전 병원 전산팀의 승인과 OCS 업체의 인터페이스 규격서가 필요합니다.
 *  - 엔드포인트 주소, 인증 방식, 코드 체계는 모두 자리표시자입니다.
 *  - 환자 정보는 병원 내부망 밖으로 보내지 마세요.
 *  - 이 파일은 실행 검증을 하지 않은 뼈대입니다.
 *
 * 앱 → OCS : order(p,o,status)  sign(p,o)  cancel(p,o)  note(p,n,status)  dispo(p)
 * OCS → 앱 : onAdmit  onOrder  onAccepted  onExecuted  onResulted  (subscribe로 등록)
 */

'use strict';

/** 쓰기 권한 단계. 병원이 허용한 단계로 고정하고 화면에서 바꾸지 못하게 하세요. */
const WRITE_MODE = process.env.OCS_WRITE_MODE || 'off'; // 'off' | 'draft'

function assertWrite(kind) {
  if (WRITE_MODE === 'off') throw new Error(`읽기 전용 모드: ${kind} 쓰기가 막혀 있습니다`);
}

/* ─────────────────── FHIR R4 어댑터 ─────────────────── */
class FhirAdapter {
  /**
   * @param {object} cfg
   * @param {string} cfg.baseUrl   병원 FHIR 서버 주소 (예: https://fhir.hospital.internal/r4) — 자리표시자
   * @param {() => Promise<string>} cfg.getToken  병원이 정한 인증 방식으로 토큰을 받는 함수 (예: SMART on FHIR)
   * @param {string} cfg.codeSystem 병원 처방 코드 체계 URI — 자리표시자
   */
  constructor(cfg) { this.cfg = cfg; }

  async req(method, path, body) {
    const res = await fetch(this.cfg.baseUrl + path, {
      method,
      headers: {
        Authorization: 'Bearer ' + (await this.cfg.getToken()),
        'Content-Type': method === 'PATCH' ? 'application/json-patch+json' : 'application/fhir+json',
        Accept: 'application/fhir+json',
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) throw new Error(`FHIR ${method} ${path} → ${res.status}`);
    return res.status === 204 ? null : res.json();
  }

  resourceType(o) { return o.category === 'MED' ? 'MedicationRequest' : 'ServiceRequest'; }

  /** 오더: draft 모드에서는 status=draft로만 올립니다. */
  async order(p, o, status) {
    assertWrite('order');
    if (WRITE_MODE === 'draft' && status !== 'draft') throw new Error('초안 모드에서는 서명 전 확정 오더를 보낼 수 없습니다');
    const coding = [{ system: this.cfg.codeSystem, code: o.code, display: o.name }];
    const body = o.category === 'MED'
      ? { resourceType: 'MedicationRequest', status, intent: 'order', medicationCodeableConcept: { coding }, subject: { reference: 'Patient/' + p.patientId }, encounter: { reference: 'Encounter/' + p.encounterId } }
      : { resourceType: 'ServiceRequest', status, intent: 'order', code: { coding }, subject: { reference: 'Patient/' + p.patientId }, encounter: { reference: 'Encounter/' + p.encounterId } };
    const created = await this.req('POST', '/' + this.resourceType(o), body);
    o.remoteId = created.id;
    return created;
  }

  /** 서명: 실제로는 OCS의 전자서명 절차를 거쳐야 합니다. 서명 결과를 받는 방법은 병원과 협의가 필요합니다. */
  async sign(p, o) {
    assertWrite('sign');
    return this.req('PATCH', `/${this.resourceType(o)}/${o.remoteId}`, [{ op: 'replace', path: '/status', value: 'active' }]);
  }

  async cancel(p, o) {
    assertWrite('cancel');
    return this.req('DELETE', `/${this.resourceType(o)}/${o.remoteId}`);
  }

  async note(p, n, status) {
    assertWrite('note');
    if (n.remoteId) return this.req('PATCH', `/DocumentReference/${n.remoteId}`, [{ op: 'replace', path: '/docStatus', value: status === 'draft' ? 'preliminary' : 'final' }]);
    const created = await this.req('POST', '/DocumentReference', {
      resourceType: 'DocumentReference', status: 'current', docStatus: status === 'draft' ? 'preliminary' : 'final',
      type: { text: n.kind }, subject: { reference: 'Patient/' + p.patientId },
      content: [{ attachment: { contentType: 'text/plain; charset=utf-8', data: Buffer.from(n.text, 'utf8').toString('base64') } }],
    });
    n.remoteId = created.id;
    return created;
  }

  async dispo(p) {
    assertWrite('dispo');
    return this.req('PATCH', `/Encounter/${p.encounterId}`, [{ op: 'replace', path: '/status', value: 'finished' }]);
  }

  /**
   * 수신: 서버가 FHIR Subscription(rest-hook)을 지원하면 알림을 받고, 아니면 주기적으로 조회합니다.
   * 아래는 조회(polling) 예시입니다. 지원 여부는 병원 서버에 따라 다릅니다.
   */
  subscribe(handlers, { encounterIds, intervalMs = 15000 }) {
    let since = new Date().toISOString();
    const tick = async () => {
      const from = since; since = new Date().toISOString();
      for (const enc of encounterIds()) {
        const bundle = await this.req('GET', `/DiagnosticReport?encounter=${enc}&_lastUpdated=ge${from}&_include=DiagnosticReport:result`);
        for (const e of bundle.entry || []) if (e.resource.resourceType === 'DiagnosticReport') handlers.onResulted?.(enc, e.resource, bundle);
        const tasks = await this.req('GET', `/Task?encounter=${enc}&_lastUpdated=ge${from}`);
        for (const e of tasks.entry || []) {
          const s = e.resource.status;
          if (s === 'accepted') handlers.onAccepted?.(enc, e.resource);
          if (s === 'in-progress') handlers.onExecuted?.(enc, e.resource);
        }
      }
    };
    const id = setInterval(() => tick().catch(err => handlers.onError?.(err)), intervalMs);
    return () => clearInterval(id);
  }
}

/* ─────────────────── HL7 v2 어댑터 ─────────────────── */
/**
 * HL7 v2는 보통 병원 인터페이스 엔진과 MLLP(TCP)로 주고받습니다.
 * MLLP 연결·ACK 처리 라이브러리와 메시지 세부 필드는 병원 규격서에 맞춰야 합니다.
 * HL7 v2에는 초안 개념이 없어 draft는 앱 DB에만 보관하고, 서명 시 ORM^O01(ORC|NW)을 보냅니다.
 */
class Hl7Adapter {
  /** @param {{send:(msg:string)=>Promise<void>, onMessage:(cb:(msg:string)=>void)=>void}} mllp */
  constructor(mllp) { this.mllp = mllp; }

  async order(p, o, status) {
    assertWrite('order');
    if (status === 'draft') return null; // 앱 내부 보관
    return this.mllp.send(this.orm(p, o, 'NW'));
  }
  async sign(p, o) { assertWrite('sign'); return this.mllp.send(this.orm(p, o, 'NW')); }
  async cancel(p, o) { assertWrite('cancel'); return o.sent ? this.mllp.send(this.orm(p, o, 'CA')) : null; }
  async note(p, n, status) { assertWrite('note'); return status === 'draft' ? null : this.mllp.send(/* MDM^T02 */ ''); }
  async dispo(p) { assertWrite('dispo'); return this.mllp.send(/* ADT^A03 또는 A06 */ ''); }

  orm(p, o, control) {
    const ts = new Date().toISOString().replace(/\D/g, '').slice(0, 14);
    return [
      `MSH|^~\\&|ER-APP|ER|OCS|HOSP|${ts}||ORM^O01|${Date.now()}|P|2.5.1`,
      `PID|1||${p.regNo}^^^HOSP^MR`,
      `ORC|${control}|${o.id}|||||||${ts}`,
      `OBR|1|${o.id}||${o.code}^${o.name}^L`,
    ].join('\r');
  }

  subscribe(handlers) {
    this.mllp.onMessage(msg => {
      const type = (msg.split('\r')[0].split('|')[8] || '');
      if (type.startsWith('ADT^A04')) handlers.onAdmit?.(msg);
      else if (type.startsWith('ORU^R01')) handlers.onResulted?.(msg);
      else if (type.startsWith('ORM^O01')) {
        const orc = msg.split('\r').find(s => s.startsWith('ORC|')) || '';
        const [, ctrl, , , , status] = orc.split('|');
        if (ctrl === 'NW') handlers.onOrder?.(msg);          // OCS에서 직접 입력된 오더
        else if (status === 'IP') handlers.onAccepted?.(msg);
      }
    });
  }
}

module.exports = { FhirAdapter, Hl7Adapter, WRITE_MODE };
