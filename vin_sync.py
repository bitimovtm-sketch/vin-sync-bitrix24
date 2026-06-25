import os
import logging
import requests
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

vin_bp = Blueprint('vin_sync', __name__)

P1_WEBHOOK     = os.environ['P1_WEBHOOK']
P2_WEBHOOK     = os.environ['P2_WEBHOOK']
VIN_FIELD_P1   = os.environ['VIN_FIELD_P1']
VIN_FIELD_P2   = os.environ['VIN_FIELD_P2']
BP_TEMPLATE_ID = os.environ['BP_TEMPLATE_ID']


def b24_call(webhook: str, method: str, params: dict) -> dict:
    url = f"{webhook.rstrip('/')}/{method}"
    resp = requests.post(url, json=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


@vin_bp.route('/vin-sync', methods=['POST'])
def vin_sync():
    deal_id = request.args.get('deal_id') or request.form.get('deal_id')
    if not deal_id:
        return jsonify({'error': 'deal_id required'}), 400

    deal = b24_call(P1_WEBHOOK, 'crm.deal.get', {'id': deal_id})
    vin = deal.get('result', {}).get(VIN_FIELD_P1, '').strip()

    if not vin:
        logger.info(f"deal {deal_id}: VIN пустой, пропускаем")
        return jsonify({'status': 'skip', 'reason': 'vin is empty'}), 200

    found = b24_call(P2_WEBHOOK, 'crm.deal.list', {
        'filter': {VIN_FIELD_P2: vin},
        'select': ['ID'],
    })
    deals_p2 = found.get('result', [])

    if not deals_p2:
        logger.warning(f"VIN {vin!r} не найден на П2")
        return jsonify({'status': 'not_found', 'vin': vin}), 200

    deal_id_p2 = str(deals_p2[0]['ID'])
    logger.info(f"VIN {vin!r} → сделка П2 #{deal_id_p2}, запускаем БП {BP_TEMPLATE_ID}")

    bp = b24_call(P2_WEBHOOK, 'bizproc.workflow.start', {
        'TEMPLATE_ID': BP_TEMPLATE_ID,
        'DOCUMENT_ID': ['crm', 'CCrmDocumentDeal', deal_id_p2],
        'PARAMETERS': {},
    })

    return jsonify({
        'status': 'ok',
        'vin': vin,
        'deal_p2': deal_id_p2,
        'bp_result': bp.get('result'),
    }), 200
