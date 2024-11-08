const mapRelay = (obj, oldObj = {}) => {
  const relay = {...oldObj, ...obj}

  relay.expanded = oldObj.expanded || false

  return relay
}
