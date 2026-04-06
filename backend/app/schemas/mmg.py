from pydantic import BaseModel, ConfigDict


class CreateOrderMMGCheckoutResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: int
    provider: str
    payment_method: str
    payment_reference: str
    checkout_url: str | None = None
    amount: float
    currency: str
    status: str
    payment_verification_status: str


class CreateOrderMMGAgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: int
    provider: str
    payment_method: str
    payment_reference: str
    amount: float
    currency: str
    status: str
    payment_verification_status: str
    instructions: str | None = None


class SubmitMMGAgentPaymentRequest(BaseModel):
    submitted_reference_code: str


class SubmitMMGAgentPaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: int
    provider: str
    payment_method: str
    payment_reference: str
    status: str
    payment_verification_status: str
    message: str


class MMGCallbackResponse(BaseModel):
    order_id: int
    status: str
    payment_verification_status: str
