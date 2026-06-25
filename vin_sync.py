import os
import logging
import requests
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

vin_bp = Blueprint('vin_sync', __name__)

P1_WEBHOOK        = os.environ['P1_WEBHOOK']
P2_WEBHOOK        = os.environ['P2_WEBHOOK']
VIN_FIELD_P1      = os.environ['VIN_FIELD_P1']
VIN_FIELD_P2      = os.environ['VIN_FIELD_P2']
VIN_LAST_FIELD_P1 = os.environ['VIN_LAST_FIELD_P1']
BP_TEMPLATE_ID    = os.environ['BP_TEMPLATE_ID']


def b24_call(webhook: str, method: str, params: dict) -> dict:
    url = f"{webhook.rstrip('/')}/{method}"
    resp = requests.post(url, json=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


@vin_bp.route('/vin-sync', methods=['POST'])
def vin_sync():
    deal_id = request.args.get('deal_id') or request.form.get('deal_id')
    if not deal_id:
        return jsonify({'error': 'deal_id required'}), 400

    # 1. Берём текущий VIN и последний синхронизированный VIN со сделки П1
    deal = b24_call(P1_WEBHOOK, 'crm.deal.get', {'id': deal_id})
    deal_data = deal.get('result', {})
    vin_current = (deal_data.get(VIN_FIELD_P1) or '').strip()
    vin_last    = (deal_data.get(VIN_LAST_FIELD_P1) or '').strip()

    if not vin_current:
        logger.info(f"deal {deal_id}: VIN пустой, пропускаем")
        return jsonify({'status': 'skip', 'reason': 'vin is empty'}), 200

    # 2. Сравниваем
    if vin_current == vin_last:
        logger.info(f"deal {deal_id}: VIN не изменился ({vin_current!r}), пропускаем")
        return jsonify({'status': 'skip', 'reason': 'vin not changed'}), 200

    logger.info(f"deal {deal_id}: VIN изменился {vin_last!r} → {vin_current!r}")

    # 3. Ищем сделку на П2 по СТАРОМУ VIN
    bp_result = None
    deal_id_p2 = None

    if not vin_last:
        logger.warning(f"deal {deal_id}: старый VIN пустой, искать на П2 нечего")
    else:
        found = b24_call(P2_WEBHOOK, 'crm.deal.list', {
            'filter': {VIN_FIELD_P2: vin_last},
            'select': ['ID'],
        })
        deals_p2 = found.get('result', [])

        if deals_p2:
            deal_id_p2 = str(deals_p2[0]['ID'])
            logger.info(f"Сделка П2 #{deal_id_p2} (старый VIN {vin_last!r}), запускаем БП {BP_TEMPLATE_ID} с новым VIN {vin_current!r}")

            bp = b24_call(P2_WEBHOOK, 'bizproc.workflow.start', {
                'TEMPLATE_ID': BP_TEMPLATE_ID,
                'DOCUMENT_ID': ['crm', 'CCrmDocumentDeal', deal_id_p2],
                'PARAMETERS': {
                    'Parameter1': vin_current,
                },
            })
            bp_result = bp.get('result')
        else:
            logger.warning(f"Старый VIN {vin_last!r} не найден на П2")

    # 4. Записываем текущий VIN в служебное поле П1
    b24_call(P1_WEBHOOK, 'crm.deal.update', {
        'id': deal_id,
        'fields': {VIN_LAST_FIELD_P1: vin_current},
    })
    logger.info(f"deal {deal_id}: записали VIN_LAST = {vin_current!r}")

    return jsonify({
        'status': 'ok',
        'vin_new': vin_current,
        'vin_old': vin_last,
        'deal_p2': deal_id_p2,
        'bp_result': bp_result,
    }), 200
