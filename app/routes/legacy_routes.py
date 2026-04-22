from flask import Blueprint, redirect, url_for

legacy_bp = Blueprint("legacy_bp", __name__)


@legacy_bp.route("/pickup/request", methods=["POST"])
def legacy_pickup_request():
    return redirect(url_for("user_bp.pickup_request"), code=307)


@legacy_bp.route("/payment/process", methods=["POST"])
def legacy_payment_process():
    return redirect(url_for("user_bp.process_payment"), code=307)
