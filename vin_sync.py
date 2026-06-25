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

# Хранилище последних известных VIN: { deal_id: vin }
vin_cache = {}


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

    # 1. Берём текущий VIN с П1
    deal = b24_call(P1_WEBHOOK, 'crm.deal.get', {'id': deal_id})
    vin_current = deal.get('result', {}).get(VIN_FIELD_P1, '').strip()

    if not vin_current:
        logger.info(f"deal {deal_id}: VIN пустой, пропускаем")
        return jsonify({'status': 'skip', 'reason': 'vin is empty'}), 200

    # 2. Сравниваем с предыдущим значением
    vin_previous = vin_cache.get(deal_id)

    if vin_previous == vin_current:
        logger.info(f"deal {deal_id}: VIN не изменился ({vin_current!r}), пропускаем")
        return jsonify({'status': 'skip', 'reason': 'vin not changed'}), 200

    logger.info(f"deal {deal_id}: VIN изменился {vin_previous!r} → {vin_current!r}")

    # 3. Сохраняем новый VIN в кэш
    vin_cache[deal_id] = vin_current

    # 4. Ищем сделку на П2
    found = b24_call(P2_WEBHOOK, 'crm.deal.list', {
        'filter': {VIN_FIELD_P2: vin_current},
        'select': ['ID'],
    })
    deals_p2 = found.get('result', [])

    if not deals_p2:
        logger.warning(f"VIN {vin_current!r} не найден на П2")
        return jsonify({'status': 'not_found', 'vin': vin_current}), 200

    deal_id_p2 = str(deals_p2[0]['ID'])
    logger.info(f"VIN {vin_current!r} → сделка П2 #{deal_id_p2}, запускаем БП {BP_TEMPLATE_ID}")

    # 5. Запускаем бизнес-процесс на П2
    bp = b24_call(P2_WEBHOOK, 'bizproc.workflow.start', {
        'TEMPLATE_ID': BP_TEMPLATE_ID,
        'DOCUMENT_ID': ['crm', 'CCrmDocumentDeal', deal_id_p2],
