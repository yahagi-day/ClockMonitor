# ClockMonitor

Raspberry Pi 5 上で動作する Stratum 1 NTP サーバー / PTP グランドマスタークロックのリアルタイム監視ダッシュボード。

ブラウザから chrony・gpsd・ptp4l・PPS・systemd の状態を確認でき、過去60分のオフセット/衛星数を時系列グラフで表示します。

## 監視項目

| セクション | 表示内容 |
|---|---|
| **System Clock** | システム時刻オフセット・RMS・周波数誤差・参照ソース一覧 |
| **NTP Server** | 受信パケット数・クライアント一覧 |
| **GPS** | Fix モード・緯度経度・使用衛星数 |
| **PTP** | portState・masterオフセット・pathDelay |
| **PPS** | 1Hz パルス確認・シーケンス番号 |
| **Services** | chrony / gpsd / ptp4l / phc2sys の起動状態 |

## 前提条件

以下がすべて動作していること。

```
chrony.service   gpsd.service   ptp4l.service   phc2sys.service
```

## セットアップ

### 1. 依存パッケージのインストール

```bash
cd /home/yahagi_day/ClockMonitor
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> `gps` と `Jinja2` はシステム site-packages から継承されます（`requirements.txt` には含めません）。

### 2. chrony の設定（初回のみ）

`/etc/chrony/chrony.conf` に以下を追加して、NTP サーバー統計を localhost から取得できるようにします。

```
cmdallow 127.0.0.1
bindcmdaddress 127.0.0.1
```

```bash
sudo systemctl restart chrony
```

### 3. sudo 権限の設定（初回のみ）

`serverstats` / `clients` の取得に root 権限が必要なため:

```bash
echo "yahagi_day ALL=(root) NOPASSWD: /usr/bin/chronyc" | sudo tee /etc/sudoers.d/clockmonitor
```

### 4. 動作確認

```bash
source .venv/bin/activate
uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8080
```

`http://192.168.1.229:8080/` をブラウザで開き、全セクションが表示されることを確認します。

### 5. systemd サービスとして登録

```bash
sudo cp clockmonitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now clockmonitor
```

## アクセス

```
http://192.168.1.229:8080/
```

LAN 内専用です。認証はありません。インターネットに公開しないでください。

## API

| エンドポイント | 内容 |
|---|---|
| `GET /` | ダッシュボード UI |
| `GET /api/health` | 死活確認 `{"ok": true}` |
| `GET /api/status` | 全ソースの現在スナップショット（JSON） |
| `GET /api/history?source=<name>&minutes=<1-60>` | 時系列データ |
| `GET /api/stream` | SSE ストリーム（約1秒間隔） |

`source` に指定できる値: `chrony_offset` / `ptp_offset_from_master` / `gps_sat_used` / `gps_sat_visible` / `pps0_seq`

## トラブルシューティング

**ダッシュボードが起動しない**
```bash
journalctl -u clockmonitor -n 50
```

**chrony セクションが red**
```bash
chronyc tracking       # 動作確認
chronyc sources        # PPS が * になっているか確認
```

**GPS セクションの `x`（黄色）は正常**
NMEA シリアルの遅延（約360ms）により GPS ソースは常に falseticker 判定になります。PPS が `*` で選ばれていれば問題ありません。

**NTP Server の数値が表示されない**
```bash
sudo chronyc serverstats    # 501 が出る場合は chrony.conf と sudoers を確認
```

**PTP セクションの `data_source: journal`**
`/var/run/ptp4lro` ソケットにアクセスできない状態です。`ptp4l.conf` の `[global]` セクションに `uds_ro_address /var/run/ptp4lro` を追加して ptp4l を再起動してください。

**gpsd が応答しない**
```bash
systemctl status gpsd
cat /etc/default/gpsd    # DEVICES に /dev/ttyAMA0 が含まれているか確認
```
