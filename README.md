# DROPZONE 公開サイト（テスト環境）

https://dropzone-test.senastudio.jp

- 中身は Supabase のデータから自動で作られます。直接このリポジトリを編集する必要はありません。
- `build.yml` が10分ごとにデータの変更を確認し、変わっていればページを作り直して公開します。
- 今すぐ反映したいときは、Actions → 「公開サイトを更新」→ Run workflow。
- `backup.yml` が毎日、公開データを `backups` ブランチに JSON で保存します。
