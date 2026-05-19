# sure_sidecar.rb
require 'json'

# Read the JSON payload (we will pass this via standard input from Python)
input_data = STDIN.read
payload = JSON.parse(input_data)

account = Account.find(payload['account_id'])
created_count = 0

payload['transactions'].each do |txn|
  # Dosu's magic deduplication logic
  entry = account.entries.find_or_initialize_by(
    external_id: txn['external_id'],
    source: "akahu"
  )

  # Only write to the database if the transaction doesn't already exist
  if entry.new_record?
    entry.assign_attributes(
      date: txn['date'],
      amount: txn['amount'],
      name: txn['name'],
      currency: "NZD",
      entryable_type: "Transaction"
    )
    
    # In Sure Finance, positive amounts are expenses, negative are income
    nature = txn['amount'].to_f > 0 ? "expense" : "income"
    entry.build_entryable(nature: nature) unless entry.entryable
    
    entry.save!
    created_count += 1
    puts " -> Created: #{txn['name']} (#{txn['external_id']})"
  else
    puts " -> Skipped (already exists): #{txn['external_id']}"
  end
end

puts "SUCCESS: Imported #{created_count} new transactions."