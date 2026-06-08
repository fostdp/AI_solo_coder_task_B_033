rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "mongo1:27017", priority: 2 },
    { _id: 1, host: "mongo2:27017", priority: 1 },
    { _id: 2, host: "mongo3:27017", priority: 1 }
  ]
});

const checkStatus = () => {
  const status = rs.status();
  if (status.ok && status.members.every(m => m.stateStr === "PRIMARY" || m.stateStr === "SECONDARY")) {
    print("Replica set initialized successfully");
    return true;
  }
  return false;
};

const waitForReplicaSet = () => {
  for (let i = 0; i < 30; i++) {
    try {
      if (checkStatus()) return;
    } catch (e) {
      print(`Waiting for replica set... (${i + 1}/30)`);
    }
    sleep(2000);
  }
  print("WARNING: Replica set may not be fully initialized");
};

waitForReplicaSet();

const primaryInfo = rs.isMaster();
if (primaryInfo.ismaster) {
  const config = rs.conf();
  config.settings = config.settings || {};
  config.settings.readPreference = "nearest";
  config.settings.readConcern = { level: "majority" };
  config.settings.writeConcern = { w: "majority", wtimeout: 5000 };
  rs.reconfig(config);
  print("Replica set configuration updated");
}
