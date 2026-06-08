const waitForShardReady = () => {
  for (let i = 0; i < 30; i++) {
    try {
      const result = sh.status();
      if (result.ok !== undefined) return true;
    } catch (e) {
      print(`Waiting for shard... (${i + 1}/30)`);
      sleep(2000);
    }
  }
  return false;
};

if (waitForShardReady()) {
  print("Shard router is ready");

  try {
    sh.addShard("rs0/mongo1:27017,mongo2:27017,mongo3:27017");
    print("Shard rs0 added successfully");
  } catch (e) {
    print(`Shard may already exist: ${e.message}`);
  }

  const databases = [
    { name: "utility_tunnel", enableSharding: true }
  ];

  databases.forEach(dbConfig => {
    try {
      sh.enableSharding(dbConfig.name);
      print(`Sharding enabled for database: ${dbConfig.name}`);
    } catch (e) {
      print(`Sharding already enabled for ${dbConfig.name}: ${e.message}`);
    }
  });

  const collections = [
    { db: "utility_tunnel", coll: "sensor_data", shardKey: { device_id: "hashed" } },
    { db: "utility_tunnel", coll: "alarms", shardKey: { timestamp: 1 } },
    { db: "utility_tunnel", coll: "devices", shardKey: { chamber: 1, type: 1 } },
    { db: "utility_tunnel", coll: "control_commands", shardKey: { timestamp: 1 } }
  ];

  collections.forEach(colConfig => {
    try {
      const fullName = `${colConfig.db}.${colConfig.coll}`;
      sh.shardCollection(fullName, colConfig.shardKey);
      print(`Collection sharded: ${fullName} with key: ${JSON.stringify(colConfig.shardKey)}`);
    } catch (e) {
      print(`Collection may already be sharded: ${e.message}`);
    }
  });

  try {
    db.getSiblingDB("utility_tunnel").sensor_data.createIndex({ timestamp: 1, device_id: 1 });
    db.getSiblingDB("utility_tunnel").alarms.createIndex({ level: 1, timestamp: 1 });
    db.getSiblingDB("utility_tunnel").devices.createIndex({ location: "2dsphere" });
    print("Indexes created successfully");
  } catch (e) {
    print(`Indexes may already exist: ${e.message}`);
  }

  print("Sharding configuration complete");
} else {
  print("ERROR: Shard router failed to become ready");
}
