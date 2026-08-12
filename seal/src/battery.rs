pub struct BatteryInfo {
    pub capacity: u8,
    pub on_ac: bool,
    pub present: bool,
}

pub fn read() -> BatteryInfo {
    let capacity = read_file("/sys/class/power_supply/BAT0/capacity")
        .and_then(|s| s.trim().parse().ok())
        .unwrap_or(100);
    let on_ac = read_file("/sys/class/power_supply/ADP0/online")
        .map(|s| s.trim() == "1")
        .unwrap_or(true);
    let present = read_file("/sys/class/power_supply/BAT0/present")
        .map(|s| s.trim() == "1")
        .unwrap_or(false);

    BatteryInfo {
        capacity,
        on_ac,
        present,
    }
}

fn read_file(path: &str) -> Option<String> {
    std::fs::read_to_string(path).ok()
}
