package payments

import org.springframework.http.HttpStatus
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.jdbc.core.RowMapper
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import org.springframework.web.server.ResponseStatusException
import java.util.UUID

@Service
open class PaymentService(private val db: JdbcTemplate) {
    private val paymentRow = RowMapper { row, _ ->
        Payment(row.getObject("id", UUID::class.java), row.getLong("sender"),
            row.getLong("recipient"), row.getLong("amount"), row.getString("status"))
    }

    open fun get(id: UUID): Payment =
        db.query("SELECT * FROM payments WHERE id = ?", paymentRow, id).firstOrNull()
            ?: throw ResponseStatusException(HttpStatus.NOT_FOUND, "Платёж не найден")

    @Transactional
    open fun transfer(key: String, request: Transfer): Payment {
        val (sender, recipient, amount) = request
        if (amount <= 0 || sender == recipient || key.isBlank() || key.length > 128) {
            throw ResponseStatusException(HttpStatus.BAD_REQUEST, "Проверьте сумму, счета и ключ запроса")
        }

        val balances = db.query(
            "SELECT id, balance FROM accounts WHERE id IN (?, ?) ORDER BY id FOR UPDATE",
            RowMapper { row, _ -> row.getLong("id") to row.getLong("balance") }, sender, recipient
        ).toMap()
        val existing = db.query(
            "SELECT * FROM payments WHERE sender = ? AND request_key = ?", paymentRow, sender, key
        ).firstOrNull()
        if (existing != null) {
            if (existing.recipient != recipient || existing.amount != amount) {
                throw ResponseStatusException(HttpStatus.CONFLICT, "Ключ уже использован с другими параметрами")
            }
            return existing
        }
        if (balances.size != 2) {
            throw ResponseStatusException(HttpStatus.NOT_FOUND, "Счёт не найден")
        }

        val enoughFunds = balances.getValue(sender) >= amount
        if (enoughFunds) {
            db.update("UPDATE accounts SET balance = balance - ? WHERE id = ?", amount, sender)
            db.update("UPDATE accounts SET balance = balance + ? WHERE id = ?", amount, recipient)
        }
        val status = if (enoughFunds) "SUCCEEDED" else "DECLINED"
        val payment = Payment(UUID.randomUUID(), sender, recipient, amount, status)
        db.update(
            "INSERT INTO payments (id, sender, recipient, amount, request_key, status) VALUES (?, ?, ?, ?, ?, ?)",
            payment.id, sender, recipient, amount, key, status
        )
        return payment
    }
}
