export $(grep -v '^#' secret.env | xargs)
export $(grep -v '^#' protocol_id.env | xargs)